"""
WebSocket origin validation.

The trap this pins down: the handshake Origin is the *frontend's* host
(chat.example.edu) while ALLOWED_HOSTS holds the API's own host
(chat-api.example.edu). Wiring the socket through AllowedHostsOriginValidator
looks right and rejects every real browser connection with a 403, while
ordinary HTTP keeps working -- so it only shows up in the browser.
"""

import pytest
from channels.testing import WebsocketCommunicator

from config.asgi import build_websocket_application

FRONTEND = "https://chat.example.edu"
API_HOST = "chat-api.example.edu"

CLOSE_UNAUTHENTICATED = 4401


async def connect(allowed_origins, origin):
    app = build_websocket_application(allowed_origins)
    comm = WebsocketCommunicator(
        app,
        "/ws/echo/",
        headers=[(b"origin", origin.encode()), (b"host", API_HOST.encode())],
    )
    connected, code = await comm.connect()
    await comm.disconnect()
    return connected, code


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_frontend_origin_passes_validation():
    """
    Reaching the consumer -- which then rejects the connection as
    unauthenticated (4401) -- is the proof that origin validation let it
    through. The validator denies with a plain close instead.
    """
    connected, code = await connect([FRONTEND, API_HOST], FRONTEND)
    assert connected is False
    assert code == CLOSE_UNAUTHENTICATED


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_unknown_origin_is_denied_before_the_consumer():
    connected, code = await connect([FRONTEND, API_HOST], "https://evil.example.com")
    assert connected is False
    assert code != CLOSE_UNAUTHENTICATED


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_api_host_alone_rejects_the_frontend():
    """
    Regression guard for the AllowedHostsOriginValidator failure mode: allowing
    only this API's own hostname locks out the frontend entirely.
    """
    connected, code = await connect([API_HOST], FRONTEND)
    assert connected is False
    assert code != CLOSE_UNAUTHENTICATED
