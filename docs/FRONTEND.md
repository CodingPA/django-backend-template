# Frontend contract

For the Next.js frontend.
[next-js-template](https://github.com/CodingPA/next-js-template) already
implements the login, signup, and WebSocket parts of this contract, so start
from it rather than from scratch. It does not yet have the
`/auth/password/reset/{key}` and `/auth/verify-email/{key}` pages that this
backend's emails link to.

## Two schemas, so you do not hand-write types

| URL | Covers |
| --- | --- |
| `/api/schema/` | This project's endpoints (OpenAPI 3, `drf-spectacular`). |
| `/api/docs/` | Human-readable Redoc for the above. |
| `/_allauth/openapi.html` | Every allauth auth endpoint. |

Generate a typed client from `/api/schema/` rather than maintaining types by
hand — that is what makes the two-repo split cheap. `openapi-typescript` or
`orval` both work.

```
uv run python manage.py spectacular --file schema.yaml
```

## Cookies and CSRF

Session cookies, scoped to the shared parent domain. There is no token to store,
nothing in `localStorage`, and no refresh timer.

Every request needs `credentials: "include"`, and every mutating request needs
the CSRF header:

```ts
function csrfToken() {
  return document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/)?.[1] ?? ""
}

export async function api(path: string, init: RequestInit = {}) {
  return fetch(`${process.env.NEXT_PUBLIC_API_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.method && init.method !== "GET"
        ? { "X-CSRFToken": csrfToken() }
        : {}),
      ...init.headers,
    },
  })
}
```

The CSRF cookie is deliberately **not** `HttpOnly` — you have to read it. The
session cookie is.

**Read the CSRF cookie fresh on every request**, as the helper above does.
Django rotates the token on login, so a value captured at page load is stale
immediately afterwards and the first post-login mutation will 403.

If you call the API from a Next.js **server** component or route handler, cookies
are not forwarded automatically; pass them through explicitly, or keep auth-bound
calls on the client.

## Bootstrapping

```
GET /api/config/
{
  "project_name": "My Project",
  "project_slug": "myproject",
  "signup_enabled": true,
  "signup_requires_access_code": false,
  "social_providers": ["google"]
}
```

Drives the app name, whether to render the signup form, whether to ask for an
access code, and which social buttons to show.

```
GET /_allauth/browser/v1/auth/session
    200 -> {"data": {"user": {...}}}
    401 -> not signed in
```

Call on load for auth state.

**`user.id` is an opaque 8-character string** (`"VW9HGKDB"`), not a number —
type it as `string` in any hand-written or generated client. It's the primary
key, generated from an alphabet with no visually confusable characters, so a
URL or log line never leaks signup order or account count the way a
sequential integer would.

## Email and password

```
POST   /_allauth/browser/v1/auth/signup   {email, password, access_code?}
POST   /_allauth/browser/v1/auth/login    {email, password}
DELETE /_allauth/browser/v1/auth/session
POST   /_allauth/browser/v1/auth/password/request  {email}
POST   /_allauth/browser/v1/auth/password/reset    {key, password}
```

Logout (`DELETE .../auth/session`) responds **401**, not 200 — the body is the
new, unauthenticated session state. That is success, not failure.

Errors:

```json
{"status": 400, "errors": [{"message": "...", "code": "email_taken", "param": "email"}]}
```

Switch on `code`, never on `message`.

## Google

```ts
// A form POST, not fetch — this is a browser redirect.
const form = document.createElement("form")
form.method = "POST"
form.action = `${API}/_allauth/browser/v1/auth/provider/redirect`
for (const [k, v] of Object.entries({
  provider: "google",
  callback_url: `${window.location.origin}/auth/callback`,
  process: "login",
  csrfmiddlewaretoken: csrfToken(),
})) {
  const input = document.createElement("input")
  input.type = "hidden"; input.name = k; input.value = v
  form.appendChild(input)
}
document.body.appendChild(form)
form.submit()
```

The user comes back to `callback_url`. **Failures arrive as query parameters,
not JSON**, because this leg is a redirect:

```
/auth/callback?error=email_taken_by_password&error_process=login
```

So `/auth/callback` needs to handle both outcomes: no `error` means check the
session endpoint and continue; an `error` means render the message below.

## Error codes to handle

| Code | Where | Suggested message |
| --- | --- | --- |
| `email_taken` | JSON, signup | "An account with this email already exists." |
| `email_taken_by_password` | query param | "This email uses a password. Sign in with your password." |
| `email_taken_by_provider` | query param | "This email uses Google. Sign in with Google." |
| `email_taken_no_method` | query param | "This account has no sign-in method. Contact support." |
| `signup_closed` | query param | "Sign-ups are currently closed." |
| `access_code_required` | JSON / query param | "An access code is required." |
| `access_code_invalid` | JSON / query param | "That access code is not valid." |
| HTTP 403 on signup | — | "Sign-ups are currently closed." |

To tell the user *which* method an address uses before they submit anything —
recommended, on blur of the email field:

```
GET /api/auth/email-status/?email=someone@example.com
    200 {"exists": true, "method": "google"}   // or "password", or null
    404                                        // disclosure disabled by config
```

Handle the 404: the backend can be configured not to answer this.

## Access codes

When `signup_requires_access_code` is true, validate as the user types:

```
POST /api/auth/access-code/  {"code": "ABC123"}
    200 {"valid": true}   -> enable both Sign up and Continue with Google
    400                   -> invalid, expired or used up
    409                   -> not currently required
```

This is **required before the Google button works**, because a redirect cannot
carry a form field. The email signup may instead pass `access_code` inline in
the signup body.

## Sessions

```
GET    /_allauth/browser/v1/auth/sessions      list active devices
DELETE /_allauth/browser/v1/auth/sessions      end specific ones
POST   /api/auth/sessions/revoke-others/       end all but the current one
```

## WebSockets

```ts
const ws = new WebSocket(`${API.replace(/^http/, "ws")}/ws/echo/`)
```

The cookie is sent automatically. Close codes:

| Code | Meaning |
| --- | --- |
| `4401` | Not authenticated — send the user to log in. |
| `4403` | Session revoked or account disabled — do not reconnect silently. |

Any other close code is a normal disconnect; reconnect with backoff.

## Environment

```
NEXT_PUBLIC_API_URL=https://api.example.com
```

Locally, `http://localhost:8000`. Both host and API must be on the same parent
domain in production for the cookie to be sent.
