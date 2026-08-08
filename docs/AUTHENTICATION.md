# Authentication

Built on [django-allauth](https://docs.allauth.org) in **headless** mode:
`HEADLESS_ONLY = True`, so allauth serves JSON at `/_allauth/browser/v1/...`
and renders no HTML auth pages at all.

## Why session cookies and not JWT

The frontend and the API are expected to be siblings under one parent domain:

```
chat.example.edu       Next.js
chat-api.example.edu   this backend
```

Those are **different origins but the same site**. Different origins means CORS
is required. Same registrable domain (`example.edu`) means a `SameSite=Lax`
cookie is still sent on requests between them. A large part of what JWT setups
exist to work around is cookies *not* being sent — here they are.

What that buys:

- **WebSocket auth is free.** Channels' `AuthMiddlewareStack` reads the same
  cookie off the handshake. No token in a query string, no custom middleware.
- **No refresh-token machinery.** No rotation, no blacklist, no clock skew.
- **Revocation actually works.** See below.
- **Nothing in `localStorage`.** The cookie is `HttpOnly`, so XSS cannot read it.

If you ever deploy the frontend on an unrelated domain, this choice has to be
revisited — a `SameSite=None` cookie would work but requires HTTPS everywhere
and is increasingly restricted by browsers.

### Revocation is the strongest argument

A JWT is self-contained: once issued the server cannot take it back before it
expires. Every "revoke a JWT" design ends up as a server-side blocklist checked
on each request — which is a database lookup per request, i.e. a session with
extra steps. A session *is* that lookup, done properly.

`apps/users/services.py` exposes three levers:

| Function | Effect |
| --- | --- |
| `ban_user(user)` | `is_active = False`. Rejected by the auth backend on the very next request, so every session dies at once, tracked or not. The kill switch. |
| `invalidate_all_sessions(user, except_session_key=...)` | Ends every session (optionally sparing the caller's). Account stays usable. |
| `end_session(user, session_key)` | One device. |
| `rotate_session_auth_hash(user)` | Last resort that needs no session tracking: gives the user a new unusable password so the stored session auth hash stops matching. Works for Google-only accounts. **Destroys any existing password.** |

Per-device tracking comes from `allauth.usersessions`, which adds a user foreign
key to sessions. That is what makes "sign out of my other devices" possible —
Django alone cannot enumerate a user's sessions.

Exposed as:
- `GET`/`DELETE /_allauth/browser/v1/auth/sessions` (allauth, per device)
- `POST /api/auth/sessions/revoke-others/` (this project, convenience)
- Admin actions on the user list: *Sign out of all devices*, *Deactivate and sign out everywhere*

**Open WebSockets are the gotcha.** A socket authenticates once, at the
handshake, so revoking a session does not by itself close a connection that is
already open. Every function above therefore also broadcasts to a per-user
channel group, and consumers close on receipt. There is a periodic re-check as a
backstop. See [WEBSOCKETS.md](WEBSOCKETS.md).

## Cookie configuration

```
SESSION_COOKIE_DOMAIN   = .example.edu        # COOKIE_DOMAIN
SESSION_COOKIE_SAMESITE = Lax                 # COOKIE_SAMESITE
SESSION_COOKIE_SECURE   = True                # COOKIE_SECURE (defaults to not DEBUG)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY    = False               # the frontend must read it
CSRF_TRUSTED_ORIGINS    = https://chat.example.edu
CORS_ALLOWED_ORIGINS    = https://chat.example.edu
CORS_ALLOW_CREDENTIALS  = True
```

`manage.py check` warns (`auth.W004`) if `COOKIE_DOMAIN` is unset with `DEBUG`
off, because the symptom otherwise is a login that appears to succeed and then
does not stick.

## The two login flows

### Email and password — plain JSON

```
POST   /_allauth/browser/v1/auth/signup    {email, password, access_code?}
POST   /_allauth/browser/v1/auth/login     {email, password}
GET    /_allauth/browser/v1/auth/session   -> current user, or 401
DELETE /_allauth/browser/v1/auth/session   -> log out
POST   /_allauth/browser/v1/auth/password/request
POST   /_allauth/browser/v1/auth/password/reset
```

### Google — a browser redirect, because OAuth requires one

```
chat.example.edu
    │  POST /_allauth/browser/v1/auth/provider/redirect
    │      {provider: "google", callback_url: "...", process: "login"}
    ▼
chat-api.example.edu ──302──▶ accounts.google.com
                                      │  user consents
                                      ▼
        /accounts/google/login/callback/   ← register this URI with Google
                    │  creates or finds the user, sets the session cookie
                    ▼
        302 back to callback_url on the frontend
```

The redirect URI to register in the Google Cloud console is
`https://<your-api-host>/accounts/google/login/callback/` — the API host, not
the frontend. Add `http://localhost:8000/accounts/google/login/callback/` for
development.

Because this leg is a browser redirect, **failures arrive as query parameters,
not JSON**: `?error=<code>&error_process=login` on your callback URL.

## One email address, one authentication method

If someone signs up with a password and later clicks *Continue with Google* on
the same address — or the reverse — the request is **refused, not linked**.

`SOCIALACCOUNT_EMAIL_AUTHENTICATION = False` disables allauth's auto-linking,
and `SocialAccountAdapter.pre_social_login` turns the collision into a specific
error rather than dumping the user on a signup form.

Auto-linking is an account-takeover vector for any provider that does not verify
email ownership: register a social identity claiming someone's address and you
inherit their account. Google does verify, so linking *could* be made safe for
Google specifically — but the safe general shape is "log in first, then connect
Google from account settings", which is an authenticated action. The adapter is
structured so that is a small addition if you want it later.

### Error codes

| Situation | Where it surfaces | Code |
| --- | --- | --- |
| Google login, address has a password account | redirect query param | `email_taken_by_password` |
| Google login, address has another provider | redirect query param | `email_taken_by_provider` |
| Google login, address has an account with no usable sign-in method | redirect query param | `email_taken_no_method` |
| Email signup, address already registered | JSON `errors[]` | `email_taken` |
| Signup disabled, email path | HTTP 403 | — |
| Signup disabled, Google path | redirect query param | `signup_closed` |
| Access code required, not supplied | JSON `errors[]` / redirect param | `access_code_required` |
| Access code wrong, expired or used up | JSON `errors[]` / redirect param | `access_code_invalid` |

The email path reports a plain `email_taken` rather than naming the provider,
because that error comes from inside allauth. To render *"this address uses
Google, sign in with Google"*, call:

```
GET /api/auth/email-status/?email=...
    -> {"exists": true, "method": "google"}
```

Best used proactively — on blur of the email field — so the user never fills in
a password they cannot use.

## Account enumeration: `AUTH_DISCLOSE_ACCOUNT_EXISTENCE`

Everything above tells an anonymous caller whether an address is registered and
how it signs in. That is **account enumeration**, and it is a deliberate choice:
the alternative UX is genuinely bad. Most consumer apps make the same trade.

Set `AUTH_DISCLOSE_ACCOUNT_EXISTENCE=False` to give it up:

- `/api/auth/email-status/` returns **404**. The whole disclosure surface this
  project adds is behind that one endpoint.
- Google collisions report a generic `email_taken` with no method named.
- `ACCOUNT_PREVENT_ENUMERATION` is switched on, so allauth responds to a
  duplicate signup as though a verification email had been sent, and mails the
  existing account instead.

> **This only fully works with `ACCOUNT_EMAIL_VERIFICATION=mandatory`.**
> Enumeration prevention works by *swallowing* the duplicate signup and sending
> an email in its place. With verification off there is no email to send, so
> allauth reports `email_taken` anyway — uniqueness wins over concealment.
> `manage.py check` warns about this combination (`auth.W001`).

## Email verification

`ACCOUNT_EMAIL_VERIFICATION` is `none` | `optional` | `mandatory`, and ships as
**`none`** so a fresh clone needs no SMTP server.

| Value | Behaviour |
| --- | --- |
| `none` | Nothing sent, nothing blocked. |
| `optional` | Verification email sent, login not blocked. |
| `mandatory` | Login blocked until the address is confirmed. |

The full path is wired regardless of the setting, so flipping it is one
environment variable:

- Verification and password-reset endpoints are always mounted.
- `EMAIL_BACKEND` defaults to the console backend, so in development the links
  print to your terminal and are clickable — no mail server needed.
- Confirmation links point at the **frontend** via `HEADLESS_FRONTEND_URLS`, not
  at a Django page.
- Sending goes through Celery (`AccountAdapter.send_mail`), so a slow SMTP
  server cannot stall a signup response.

**Google signups are pre-verified** — allauth trusts Google's `email_verified`
claim (`VERIFIED_EMAIL: True`) — so even under `mandatory` a Google user never
sees a verification step. Only password signups do.

Password reset needs working email anyway, so the day you configure SMTP is the
natural day to move to `mandatory`. `manage.py check` warns (`auth.W002`) if
verification is on while mail still goes to the console.

## The user model

`apps/users/models.py` defines a custom `User` with email as `USERNAME_FIELD`
and no `username`. It exists from the first migration on purpose: swapping
`AUTH_USER_MODEL` on a populated database is painful, and Google-primary auth
makes email-as-identity the right shape.
