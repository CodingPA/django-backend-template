# Starting a new project from this template

The rename is one file. Nothing in the Python source is named after the project
— the Django package is called `config` permanently, and the display name comes
from the environment.

## 1. Clone

```
git clone <this repo> my-new-backend
cd my-new-backend
rm -rf .git && git init
```

## 2. Install

```
uv sync
```

If `uv` is not installed, get it from https://docs.astral.sh/uv/ — do not rely
on a copy bundled inside another application.

## 3. Configure

```
cp .env.example .env
```

Edit the identity block. In development this is genuinely all that is required:

```
PROJECT_NAME="Chat"
PROJECT_SLUG=chat
PROJECT_DESCRIPTION="Backend API for Chat"
```

`PROJECT_SLUG` also names the session cookie (`chat_sessionid`), which lets two
projects share a parent domain without colliding.

## 4. Run

```
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

No Docker, no Redis, no Postgres. SQLite, an in-memory channel layer, inline
Celery tasks, and console email are the defaults. Check it:

```
curl http://localhost:8000/api/health/
curl http://localhost:8000/api/config/
```

## 5. Add Google login

1. Google Cloud console → APIs & Services → Credentials → OAuth client ID → Web
   application.
2. Authorised redirect URIs — the **API** host, not the frontend:
   ```
   http://localhost:8000/accounts/google/login/callback/
   https://chat-api.example.edu/accounts/google/login/callback/
   ```
3. Put the credentials in `.env`:
   ```
   GOOGLE_CLIENT_ID=...
   GOOGLE_CLIENT_SECRET=...
   ```

## 6. Build your app

```
uv run python manage.py startapp thing apps/thing
```

Then:
- Set `name = "apps.thing"` and `label = "thing"` in `apps/thing/apps.py`.
- Add `"apps.thing"` to `INSTALLED_APPS`.
- Add URLs to `config/urls.py`.
- For WebSockets, create `apps/thing/routing.py` and include it in
  `config/routing.py`.

Keep reading [ARCHITECTURE.md](ARCHITECTURE.md).

## 7. Wire up the frontend

Hand [FRONTEND.md](FRONTEND.md) to whoever is building the Next.js app. It has
the endpoints, the cookie and CSRF rules, the error codes, and the WebSocket
close codes.

## What you should **not** need to change

| | |
| --- | --- |
| `config/` package name | Renaming it buys nothing and breaks `DJANGO_SETTINGS_MODULE`, `manage.py`, `asgi.py`, `wsgi.py` and `celery.py`. |
| `apps/users/models.py` `User` | Add fields if you need them, but keep email as `USERNAME_FIELD`. Swapping `AUTH_USER_MODEL` later is painful. |
| The adapters | Unless you are changing auth policy. Read [AUTHENTICATION.md](AUTHENTICATION.md) first. |

## Before going live

See [DEPLOYMENT.md](DEPLOYMENT.md). The short version:

```
DEBUG=False
SECRET_KEY=<64 random bytes>
ALLOWED_HOSTS=chat-api.example.edu
FRONTEND_URL=https://chat.example.edu
COOKIE_DOMAIN=.example.edu
DATABASE_URL=postgres://...
REDIS_URL=redis://...
```

then

```
uv run python manage.py check --deploy
```
