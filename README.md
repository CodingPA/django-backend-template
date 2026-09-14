# Django Backend Template

[![CI](https://github.com/CodingPA/django-backend-template/actions/workflows/ci.yml/badge.svg)](https://github.com/CodingPA/django-backend-template/actions/workflows/ci.yml)

A reusable Django backend to clone into new projects. Google + email auth,
WebSockets, background tasks, and feature-flagged signup — configured entirely
through environment variables, so starting a new project means editing `.env`,
not renaming Python modules.

Pairs with a separate Next.js frontend repository.

## What is in it

| | |
| --- | --- |
| **Auth** | django-allauth headless. Google OAuth + email/password, session cookies, password reset, email verification. |
| **Signup control** | `SIGNUP_ENABLED` and `SIGNUP_REQUIRES_ACCESS_CODE`, enforced on every path into the user table. |
| **Access codes** | Revocable, expiring, use-limited invite codes with a redemption audit trail. |
| **Realtime** | Channels over ASGI, authenticated by the same cookie as the REST API. |
| **Tasks** | Celery with django-celery-beat for database-editable schedules. |
| **API contract** | OpenAPI schema at `/api/schema/`, so the frontend generates a typed client. |
| **Revocation** | Per-device session management, ban, sign-out-everywhere — including closing live WebSockets. |

Postgres and Redis in production; SQLite and in-process everything in
development.

## Quick start

```bash
uv sync
cp .env.example .env
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

That is the whole setup. **No Docker, no Redis, no Postgres required** — with
`DATABASE_URL` and `REDIS_URL` unset you get SQLite, an in-memory channel layer,
inline Celery tasks, and email printed to your terminal. Setting those variables
switches each service over with no code change.

```bash
curl http://localhost:8000/api/health/
curl http://localhost:8000/api/config/
```

| URL | |
| --- | --- |
| `/admin/` | Django admin |
| `/api/docs/` | API reference |
| `/api/schema/` | OpenAPI schema |
| `/_allauth/openapi.html` | Auth endpoint reference |

## Using it for a new project

```bash
git clone <this repo> my-new-backend
cd my-new-backend && rm -rf .git && git init
cp .env.example .env
```

Then edit three lines:

```
PROJECT_NAME="Chat"
PROJECT_SLUG=chat
PROJECT_DESCRIPTION="Backend API for Chat"
```

The Django package stays `config` forever, so there is nothing to find and
replace. Full walkthrough in [docs/NEW_PROJECT.md](docs/NEW_PROJECT.md).

## Documentation

| | |
| --- | --- |
| [NEW_PROJECT.md](docs/NEW_PROJECT.md) | Clone-to-running checklist. |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layout and the two decisions that shape it. |
| [AUTHENTICATION.md](docs/AUTHENTICATION.md) | Sessions vs JWT, both login flows, account collisions, revocation. |
| [FEATURE_FLAGS.md](docs/FEATURE_FLAGS.md) | Signup flags and access codes. |
| [CONFIGURATION.md](docs/CONFIGURATION.md) | Every environment variable. |
| [WEBSOCKETS.md](docs/WEBSOCKETS.md) | Channels, consumers, closing revoked sockets. |
| [BACKGROUND_TASKS.md](docs/BACKGROUND_TASKS.md) | Celery, eager mode, Windows workers. |
| [FRONTEND.md](docs/FRONTEND.md) | The contract for the Next.js repo. |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production checklist. |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Dev setup and what to check before a PR. |
| [SECURITY.md](SECURITY.md) | Reporting a vulnerability. |

## A few decisions worth knowing up front

**Session cookies, not JWT.** The frontend and API are expected to be siblings
under one parent domain (`chat.example.edu` / `chat-api.example.edu`) — the same
site, so the cookie is simply sent. That makes WebSocket auth free and makes
revocation real: a session can be deleted, a JWT cannot be recalled.

**One email address, one authentication method.** A Google login for an address
that already has a password account is refused rather than silently linked, and
the error names the method the account actually uses so the frontend can point
the user at the right door. Auto-linking is an account-takeover vector.

**Signup flags close every path.** There are three ways an account gets created
— email signup, Google-as-new-user, and Google-hitting-an-existing-address — and
all three are gated. The failure mode this guards against is a "signup disabled"
deployment that still lets people in through Google.

**Account enumeration is a setting.** Helpful errors like "this email uses
Google" tell anonymous callers that an address is registered. That is on by
default because the alternative UX is bad; `AUTH_DISCLOSE_ACCOUNT_EXISTENCE=False`
turns it off. See the caveat in
[AUTHENTICATION.md](docs/AUTHENTICATION.md#account-enumeration-auth_disclose_account_existence).

## Development

```bash
uv run pytest                              # tests
uv run ruff check . && uv run ruff format .
uv run python manage.py check --deploy     # config audit
```

With Redis running, for the real thing:

```bash
uv run celery -A config worker --loglevel=info --pool=solo   # --pool=solo on Windows
uv run celery -A config beat --loglevel=info
```

## Requirements

Python 3.12+, [uv](https://docs.astral.sh/uv/). Postgres and Redis in
production only.
