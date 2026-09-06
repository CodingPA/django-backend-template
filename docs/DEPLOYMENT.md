# Deployment

## Processes

Three, and they are separate:

```
# Web — must be ASGI. A WSGI server cannot serve WebSockets.
uvicorn config.asgi:application --host 0.0.0.0 --port 8000

# Worker
celery -A config worker --loglevel=info --concurrency=4

# Scheduler — exactly one, or every periodic task double-fires.
celery -A config beat --loglevel=info
```

`daphne config.asgi:application` works equally well for the web process.

## Docker

```
cp .env.example .env      # edit PROJECT_NAME etc. — leave DATABASE_URL/REDIS_URL unset
docker compose up --build
```

`docker-compose.yml` runs all three processes above plus Postgres and Redis —
`web` (daphne), `worker`, `beat`, `db`, `redis`. `DATABASE_URL` and
`REDIS_URL` are set in the compose file to point at the `db` and `redis`
services and override whatever is in `.env`, so you do not need to fill those
two in yourself; everything else (`PROJECT_NAME`, `SECRET_KEY`,
`GOOGLE_CLIENT_ID`, feature flags, ...) still comes from `.env`.

Only `web` runs `migrate` on startup — `worker` and `beat` wait on `db`/`redis`
being healthy but not on migrations being applied, so on a brand new volume
give `web` a few seconds' head start before it matters (Celery has nothing to
do until a task is queued, and `beat`'s own tables are what `migrate`
creates).

The image runs `collectstatic` at build time and serves through WhiteNoise, so
there is no separate static container or volume to wire up. Rebuild
(`docker compose up --build`) after any static asset or dependency change; a
plain `up` reuses the last image.

This is a starting point for local parity with Postgres/Redis, or as the base
for a real deployment — it has no TLS termination, so put a reverse proxy in
front of `web` for anything public, and see "What DEBUG=False turns on" below
for `SECURE_PROXY_SSL_HEADER`.

## Required environment

```
DEBUG=False
SECRET_KEY=<python -c "import secrets; print(secrets.token_urlsafe(64))">
ALLOWED_HOSTS=chat-api.example.edu
FRONTEND_URL=https://chat.example.edu
COOKIE_DOMAIN=.example.edu
DATABASE_URL=postgres://user:pass@host:5432/dbname
REDIS_URL=redis://host:6379/0
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
ADMIN_URL=<something-unguessable>/
```

Settings raises at startup if `SECRET_KEY` is empty while `DEBUG` is off, rather
than booting with a broken one.

## Deploy sequence

```
uv sync --no-dev
uv run python manage.py check --deploy     # resolve warnings first
uv run python manage.py migrate
uv run python manage.py collectstatic --noinput
```

Static files are served by WhiteNoise with compression and manifest hashing, so
the admin works without a separate static host.

## What `DEBUG=False` turns on

`SECURE_SSL_REDIRECT`, HSTS for a year with subdomains and preload,
`SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS=DENY`, secure session and CSRF
cookies, and `SECURE_PROXY_SSL_HEADER` for running behind a TLS-terminating
proxy.

If your proxy does not set `X-Forwarded-Proto`, remove that last one — trusting
a header the proxy does not actually set lets a client claim HTTPS.

## The checks worth reading

`manage.py check --deploy` adds four project-specific warnings on top of
Django's:

| ID | Why it matters |
| --- | --- |
| `auth.W001` | `AUTH_DISCLOSE_ACCOUNT_EXISTENCE=False` silently does nothing without mandatory email verification. |
| `auth.W002` | Verification emails are going to the console, i.e. nowhere. |
| `auth.W003` | Google login is installed but unconfigured. |
| `auth.W004` | `COOKIE_DOMAIN` unset — login will appear to succeed and not stick. |
| `auth.W005` | The frontend host is not allowed to open WebSockets — every socket 403s while HTTP looks fine. |

`auth.W004` and `auth.W005` are the two that cost an afternoon if ignored: both
fail in a way that looks like a frontend bug.

## Health checks

```
GET /api/health/
    200 {"status": "ok", "database": "ok"}
    503 {"status": "degraded", "database": "error"}
```

Point your load balancer here. It touches the database, so it is a readiness
probe, not just liveness.

## Redis

Required in production, for three things:

- **Channel layer** — the in-memory fallback does not span processes, so group
  sends silently miss sockets held by another worker.
- **Sessions** — keeps revocation checks off Postgres.
- **Celery broker.**

One instance is fine for all three.

## Scaling notes

- The web process is stateless. Scale horizontally.
- Sticky sessions are **not** required; both sessions and the channel layer are
  in Redis.
- Run `beat` once and only once.
- `DB_CONN_MAX_AGE` defaults to 60s. Behind PgBouncer in transaction mode, set
  it to `0`.

## Backups

Postgres holds users, access codes and redemptions. Redis holds sessions and
queued tasks — losing it logs everyone out and drops in-flight tasks, which is
survivable. Back up Postgres.

## Rotating a compromised `SECRET_KEY`

Changing it invalidates every session and every outstanding password-reset link.
To rotate without logging everyone out, put the old value in
`SECRET_KEY_FALLBACKS` for one deploy cycle, then remove it.
