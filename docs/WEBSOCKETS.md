# WebSockets

Django Channels over ASGI. `config/asgi.py`:

```python
"websocket": OriginValidator(
    AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    settings.WEBSOCKET_ALLOWED_ORIGINS,
)
```

- **`AuthMiddlewareStack`** reads the same session cookie the REST API uses and
  populates `scope["user"]`. No tokens, no query-string credentials.
- **`OriginValidator`** checks the handshake `Origin`. Without it, a page on any
  origin could open a socket against your API using the visitor's ambient
  cookie — CORS does not apply to WebSockets.

## Why not `AllowedHostsOriginValidator`

Channels ships `AllowedHostsOriginValidator`, and almost every tutorial uses it.
It is wrong for this deployment shape, in a way that only shows up in a browser.

It validates the handshake `Origin` against `ALLOWED_HOSTS`. But `ALLOWED_HOSTS`
holds **this API's** hostnames (`chat-api.example.edu`), while the `Origin` on
the handshake is the **frontend's** (`chat.example.edu`). They never match, so
every legitimate connection is denied with a 403 — while ordinary HTTP keeps
working perfectly, because CORS is configured separately and correctly.

`WEBSOCKET_ALLOWED_ORIGINS` therefore defaults to `CORS_ALLOWED_ORIGINS +
ALLOWED_HOSTS`: the frontend, plus this API's own hosts for same-origin tools.
Override it explicitly if you need something else.

`manage.py check` reports `auth.W005` if `FRONTEND_URL`'s host is missing from
it. `apps/realtime/test_origin.py` pins the behaviour, including a regression
test for the `AllowedHostsOriginValidator` failure mode.

## Writing a consumer

Subclass `AuthenticatedConsumer` from `apps/realtime/consumers.py` and implement
`receive_json`:

```python
from apps.realtime.consumers import AuthenticatedConsumer


class NotificationConsumer(AuthenticatedConsumer):
    async def connect(self):
        self.groups_for_user = (f"notify.{self.scope['user'].pk}",)
        await super().connect()

    async def receive_json(self, content, **kwargs): ...
```

Register it in `apps/realtime/routing.py`; `config/routing.py` aggregates each
app's patterns.

The base class rejects anonymous connections with close code **4401**, and
`self.user` is available throughout.

`EchoConsumer` at `ws/echo/` is a placeholder so the stack is verifiable on a
fresh clone. Replace it; keep the base class.

## Revocation, and why it needs explicit work

A socket authenticates **once**, at the handshake. Deleting the session does not
close a connection that is already open — it would keep streaming to a user you
just banned. Two defences:

1. **Per-user control group.** Every consumer joins `user.<pk>.control` on
   connect. `apps/users/services.py` broadcasts `force.disconnect` to that group
   whenever a session is revoked, and the consumer sends a final
   `{"type": "disconnect", "reason": ...}` frame and closes with **4403**.

2. **Periodic re-validation.** Every `WS_REVALIDATE_INTERVAL_SECONDS` (60 by
   default) an open socket re-checks that its user is still active, as a
   backstop for a control message that never arrived.

Covered by `apps/realtime/tests.py`.

### Close codes

| Code | Meaning |
| --- | --- |
| `4401` | Not authenticated at handshake. |
| `4403` | Session revoked or account disabled while connected. |

Treat 4401 as "send the user to log in" and 4403 as "session ended, do not
reconnect silently".

## Connecting from the frontend

The cookie rides along automatically, because the socket is same-site:

```ts
const ws = new WebSocket("wss://chat-api.example.edu/ws/echo/")
```

Browsers send no custom headers on a WebSocket handshake, which is exactly why a
token-based scheme would need the token in the query string — where it lands in
server logs. Another reason the cookie approach is simpler here.

## Development vs production

With `REDIS_URL` unset the channel layer is `InMemoryChannelLayer`: fine for one
process, so `runserver` works with nothing else installed. It does **not** span
processes, so group sends will not reach sockets held by another worker.

Set `REDIS_URL` for anything with more than one process — always in production.

`runserver` speaks ASGI automatically because `daphne` is first in
`INSTALLED_APPS`. In production run `uvicorn config.asgi:application` or
`daphne config.asgi:application`; a WSGI server cannot serve WebSockets.
