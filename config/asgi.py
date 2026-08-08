import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# The HTTP application must be built before importing anything that touches
# models, so that the app registry is populated.
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import OriginValidator  # noqa: E402
from django.conf import settings  # noqa: E402

from config.routing import websocket_urlpatterns  # noqa: E402


def build_websocket_application(allowed_origins):
    """
    Assemble the WebSocket stack. Split out so tests can build one with a
    different origin list -- the list is captured at construction, so
    override_settings cannot reach the module-level instance below.

    AuthMiddlewareStack reads the same session cookie the REST API uses, so
    WebSocket auth needs no tokens.

    OriginValidator stops a page on another origin from opening a socket with
    the visitor's ambient cookie; CORS does not apply to WebSockets, so without
    it any site could do that.

    Note this is OriginValidator and NOT AllowedHostsOriginValidator. The
    handshake Origin is the *frontend's* host (chat.example.edu), while
    ALLOWED_HOSTS holds this API's host (chat-api.example.edu). Validating
    against ALLOWED_HOSTS rejects every legitimate browser connection with a
    403 while ordinary HTTP keeps working, which is a miserable thing to debug.
    """
    return OriginValidator(AuthMiddlewareStack(URLRouter(websocket_urlpatterns)), allowed_origins)


application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": build_websocket_application(settings.WEBSOCKET_ALLOWED_ORIGINS),
    }
)
