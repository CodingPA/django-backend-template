# Feature flags

Two booleans control who may create an account. Read them through
`apps/core/flags.py`, never `settings.X` directly, so the backing store can
change later without touching call sites.

```python
from apps.core import flags

flags.signup_enabled()
flags.signup_requires_access_code()
flags.disclose_account_existence()
```

| Variable | Default | Effect |
| --- | --- | --- |
| `SIGNUP_ENABLED` | `True` | When false, no new account can be created by any method. |
| `SIGNUP_REQUIRES_ACCESS_CODE` | `False` | When true, a valid `AccessCode` must be presented to sign up. |
| `AUTH_DISCLOSE_ACCOUNT_EXISTENCE` | `True` | See [AUTHENTICATION.md](AUTHENTICATION.md#account-enumeration-auth_disclose_account_existence). |

The frontend reads the first two from `GET /api/config/`:

```json
{
  "project_name": "My Project",
  "project_slug": "myproject",
  "signup_enabled": true,
  "signup_requires_access_code": false,
  "social_providers": ["google"]
}
```

## Every path a flag has to close

This is the part that is easy to get wrong. There are **three** ways an account
comes into existence, not one:

| # | Path | Guarded by |
| --- | --- | --- |
| 1 | Email + password signup | `AccountAdapter.is_open_for_signup` |
| 2 | Google login, brand new user | `SocialAccountAdapter.is_open_for_signup` |
| 3 | Google login, address already belongs to an account | `pre_social_login` |

A deployment that enforces `SIGNUP_ENABLED` in the signup serializer and leaves
Google's first-login-creates-account untouched has not disabled signup. Path 3
is a linking decision rather than a signup, which is why it needs separate
handling — without it, a closed deployment still lets someone in through an
existing address.

All three are covered by `apps/users/tests/test_signup_flags.py`, and paths 2
and 3 are driven through allauth's real social signup flow rather than by
asserting the predicate, so the tests fail if allauth ever stops consulting the
adapter.

## Access codes

`AccessCode` is a model, not a shared secret in the environment, so codes can be
revoked, expired, counted and audited individually.

| Field | Meaning |
| --- | --- |
| `code` | Uppercase, unique. Generated from an alphabet with no confusable glyphs. |
| `label` | Who it was issued to. |
| `max_uses` | `0` means unlimited. |
| `uses` | Read-only counter. |
| `expires_at` | Optional. |
| `is_active` | Revocation switch. |

Every redemption is recorded in `AccessCodeRedemption`, so you can see which
account was created with which code.

Two safeguards on the counter:

- `AccessCode.consume()` claims a use with a single conditional `UPDATE`, so two
  concurrent signups cannot both take the last use of a code.
- `access_codes.consume()` is guarded per request. Two owners can reach it for a
  single signup — `SocialAccountAdapter.save_user` and
  `SignupExtraFieldsForm.signup` — and allauth calls both on the
  social-signup-with-form path. A `max_uses=1` code happens to self-limit, but a
  multi-use or unlimited one would otherwise be charged twice and log two
  redemptions. Covered by `apps/users/tests/test_access_code_consumption.py`.

Create them in the admin — the add form pre-fills a generated code — or:

```python
from apps.users.models import AccessCode

AccessCode.objects.create(code=AccessCode.generate_code(), label="Spring pilot", max_uses=25)
```

### Why validation happens up front

Google signups have no form to hang an `access_code` field on: the user leaves
for Google and comes back already authenticated. So the code is validated first
and the result stashed in the session, and both signup paths read it from there.

```
POST /api/auth/access-code/  {"code": "ABC123"}
    200 {"valid": true}         -> stashed in the session
    400                         -> invalid, expired, exhausted or revoked
    409                         -> access codes are not currently required
```

The frontend should call this as the user types the code, then enable both
*Sign up* and *Continue with Google*.

The email path may skip the pre-flight and pass `access_code` inline to the
allauth signup endpoint instead; it is validated by the same function. Both
approaches are tested.

Invalid, expired, exhausted and revoked codes all return the identical message.
Distinguishing them would let a caller probe the code space.

## Turning signup off in practice

```
SIGNUP_ENABLED=False
```

Then:
- `GET /api/config/` reports `"signup_enabled": false`, so the frontend can hide
  the form entirely.
- The email signup endpoint returns **403**.
- Google returns the user to your callback URL with `?error=signup_closed`.
- Existing users continue to sign in normally by both methods.
