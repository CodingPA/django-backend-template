# Configuration

Everything is read from the environment by `config/settings.py`, via
`django-environ`. Copy `.env.example` to `.env` and edit. There is no
`settings/dev.py` / `settings/prod.py` split.

## Identity

| Variable | Default | Notes |
| --- | --- | --- |
| `PROJECT_NAME` | `Django Backend Template` | Admin header, OpenAPI title, email subject prefix. |
| `PROJECT_SLUG` | `backend` | Used in the session cookie name. |
| `PROJECT_DESCRIPTION` | empty | OpenAPI description. |

These are the entire "rename the project" step. The Python package stays
`config`.

## Core

| Variable | Default | Notes |
| --- | --- | --- |
| `DEBUG` | **none — required** | No default, so a deploy that forgets to set it fails at startup instead of running in debug mode. `.env.example` sets it to `True`. Off enables the hardening block at the bottom of settings. |
| `SECRET_KEY` | insecure dev value | **Required when `DEBUG=False`** — settings raises at startup otherwise. |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | Comma-separated. This API's own hostnames. |
| `ADMIN_URL` | `admin/` | Move it off the default path in production. |
| `TIME_ZONE` | `UTC` | |
| `LOG_LEVEL` | `INFO` | |

Generate a secret key:

```
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

## Frontend origin and cookies

| Variable | Default | Notes |
| --- | --- | --- |
| `FRONTEND_URL` | `http://localhost:3000` | Also the base for all `HEADLESS_FRONTEND_URLS`. |
| `CORS_ALLOWED_ORIGINS` | `[FRONTEND_URL]` | |
| `CSRF_TRUSTED_ORIGINS` | `[FRONTEND_URL]` | |
| `COOKIE_DOMAIN` | unset | Set to the shared parent, e.g. `.example.com`. `check` warns if unset with `DEBUG=False`. |
| `COOKIE_SAMESITE` | `Lax` | |
| `COOKIE_SECURE` | `not DEBUG` | |
| `SESSION_COOKIE_NAME` | `<PROJECT_SLUG>_sessionid` | Distinct names let two projects share a parent domain. |
| `SESSION_COOKIE_AGE` | 14 days | Seconds. |
| `WEBSOCKET_ALLOWED_ORIGINS` | `CORS_ALLOWED_ORIGINS + ALLOWED_HOSTS` | Origins allowed to open a WebSocket. **Not** `ALLOWED_HOSTS` — see [WEBSOCKETS.md](WEBSOCKETS.md#why-not-allowedhostsoriginvalidator). |

A production set for `app.example.com` + `api.example.com`:

```
ALLOWED_HOSTS=api.example.com
FRONTEND_URL=https://app.example.com
COOKIE_DOMAIN=.example.com
COOKIE_SECURE=True
```

## Services

| Variable | Unset behaviour | Notes |
| --- | --- | --- |
| `DATABASE_URL` | SQLite at `db.sqlite3` | `postgres://user:pass@host:5432/db` |
| `DB_CONN_MAX_AGE` | `60` | Ignored on SQLite. |
| `REDIS_URL` | In-memory channel layer, local-memory cache, DB sessions | `redis://localhost:6379/0` |
| `CELERY_BROKER_URL` | falls back to `REDIS_URL` | |
| `CELERY_RESULT_BACKEND` | falls back to `REDIS_URL` | |
| `CELERY_TASK_ALWAYS_EAGER` | `True` when no broker | Tasks run inline. |

Setting `REDIS_URL` moves sessions into Redis, which keeps revocation checks off
Postgres.

## Signup flags

| Variable | Default |
| --- | --- |
| `SIGNUP_ENABLED` | `True` |
| `SIGNUP_REQUIRES_ACCESS_CODE` | `False` |
| `AUTH_DISCLOSE_ACCOUNT_EXISTENCE` | `True` |

See [FEATURE_FLAGS.md](FEATURE_FLAGS.md).

## Google OAuth

| Variable | Notes |
| --- | --- |
| `GOOGLE_CLIENT_ID` | From the Google Cloud console. |
| `GOOGLE_CLIENT_SECRET` | |

Authorised redirect URIs to register with Google:

```
http://localhost:8000/accounts/google/login/callback/
https://api.example.com/accounts/google/login/callback/
```

That is the **API** host. `check` warns (`auth.W003`) if the client ID is unset
with `DEBUG=False`.

## Email

| Variable | Default | Notes |
| --- | --- | --- |
| `ACCOUNT_EMAIL_VERIFICATION` | `none` | `none` / `optional` / `mandatory`. |
| `EMAIL_BACKEND` | console | Mail prints to the terminal in development. |
| `EMAIL_HOST` / `EMAIL_PORT` | — / `587` | |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | empty | |
| `EMAIL_USE_TLS` | `True` | |
| `DEFAULT_FROM_EMAIL` | `noreply@localhost` | |
| `PASSWORD_MIN_LENGTH` | `10` | |

## Production only

| Variable | Default |
| --- | --- |
| `SECURE_SSL_REDIRECT` | `True` |
| `SECURE_HSTS_SECONDS` | one year |

Applied only when `DEBUG=False`, along with `SECURE_CONTENT_TYPE_NOSNIFF`,
`X_FRAME_OPTIONS=DENY`, HSTS subdomains and preload, and
`SECURE_PROXY_SSL_HEADER` for running behind a TLS-terminating proxy.

## Verifying a configuration

```
uv run python manage.py check --deploy
```

Beyond Django's own checks this reports:

| ID | Meaning |
| --- | --- |
| `auth.W001` | `AUTH_DISCLOSE_ACCOUNT_EXISTENCE=False` does nothing without `ACCOUNT_EMAIL_VERIFICATION=mandatory`. |
| `auth.W002` | Email verification is on but mail goes to the console. |
| `auth.W003` | Google login is installed but unconfigured. |
| `auth.W004` | `COOKIE_DOMAIN` unset, so the cookie will not reach a sibling subdomain. |
| `auth.W005` | The frontend host is missing from `WEBSOCKET_ALLOWED_ORIGINS`, so every socket gets a 403 while HTTP keeps working. |
