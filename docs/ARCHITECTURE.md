# Architecture

## Layout

```
config/                 Django project package. Never renamed.
  settings.py           One env-driven settings module.
  urls.py               Root URLconf.
  asgi.py               HTTP + WebSocket entry point.
  wsgi.py               HTTP-only entry point.
  routing.py            Aggregates each app's WebSocket routes.
  celery.py             Celery app.
apps/
  core/                 Health check, /api/config/, shared Celery tasks, flags.
  users/                Custom User, access codes, allauth adapters, revocation.
  realtime/             Channels consumers.
docs/
```

## Two decisions that shape everything else

### The package is called `config`, permanently

Nothing in the Python source is named after the project. The display name comes
from `PROJECT_NAME` in the environment and is consumed by the admin header, the
OpenAPI title, and email subject prefixes.

The alternative — naming the package after the project — means every clone
starts with a find-and-replace across `manage.py`, `wsgi.py`, `asgi.py`,
`celery.py`, `DJANGO_SETTINGS_MODULE`, and every import. Renaming a variable in
`.env` is the whole job here. See [NEW_PROJECT.md](NEW_PROJECT.md).

### One settings module, not base/dev/prod

`config/settings.py` reads everything from the environment. There is no
`settings/` package and no `DJANGO_SETTINGS_MODULE` juggling.

The behaviour that makes this work is that **every external service degrades to
a zero-dependency local default**:

| Variable | Unset (development) | Set (production) |
| --- | --- | --- |
| `DATABASE_URL` | SQLite file at `db.sqlite3` | Postgres |
| `REDIS_URL` | In-memory channel layer, local-memory cache, DB sessions | Redis for all three |
| `CELERY_BROKER_URL` | `CELERY_TASK_ALWAYS_EAGER` — tasks run inline | Real worker |
| `EMAIL_BACKEND` | Console — mail prints to the terminal | SMTP |

So `git clone && uv sync && cp .env.example .env && manage.py migrate &&
manage.py runserver` gives a working backend with **no Docker, no Redis, and
no Postgres installed**. A
template that needs three services running before it boots is a template nobody
uses.

Eager Celery matters for a subtler reason than convenience: without a broker,
`.delay()` would otherwise silently do nothing, and you would not find out until
production. Running inline means task code is actually exercised in dev.

## Request paths

```
HTTP        ->  daphne/uvicorn -> Django  -> DRF views + allauth headless
WebSocket   ->  daphne/uvicorn -> Channels -> AllowedHostsOriginValidator
                                           -> AuthMiddlewareStack (session cookie)
                                           -> URLRouter -> consumer
Background  ->  Celery worker  -> apps/*/tasks.py
```

`config/asgi.py` builds the Django HTTP application *before* importing anything
that touches models, because the app registry has to be populated first.

## Feature flags

Flags are environment variables, read through `apps/core/flags.py` rather than
`settings.X` directly. That indirection is the whole point: the backing store can
become a database singleton or a remote flag service later without touching any
call site. Two booleans do not justify a flag library.

## The API contract

`drf-spectacular` serves an OpenAPI schema at `/api/schema/`, and allauth serves
its own at `/_allauth/openapi.html`. With the frontend in a separate repository,
these are what keep the two in sync — the Next.js app generates a typed client
rather than hand-maintaining types. See [FRONTEND.md](FRONTEND.md).

## Testing

`pytest` with `pytest-django`. The suite is deliberately concentrated on the
security-relevant behaviour rather than spread thin:

- `apps/users/tests/test_signup_flags.py` — both flags against all signup paths
- `apps/users/tests/test_account_collisions.py` — one email, one auth method
- `apps/users/tests/test_revocation.py` — sessions really do die
- `apps/realtime/tests.py` — socket auth and forced disconnect

```
uv run pytest
```
