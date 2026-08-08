"""
WebSocket auth and the revocation path.

The subtle one is test_force_disconnect_closes_an_open_socket: sockets
authenticate once at the handshake, so without the control group an already
open connection would keep streaming after the session was revoked.
"""

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

from apps.realtime.consumers import CLOSE_REVOKED, CLOSE_UNAUTHENTICATED, EchoConsumer
from apps.users import services

User = get_user_model()


def communicator(user):
    comm = WebsocketCommunicator(EchoConsumer.as_asgi(), "/ws/echo/")
    comm.scope["user"] = user
    return comm


@pytest.mark.asyncio
async def test_anonymous_socket_is_rejected():
    comm = communicator(AnonymousUser())
    connected, code = await comm.connect()
    assert connected is False
    assert code == CLOSE_UNAUTHENTICATED


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_authenticated_socket_connects_and_echoes():
    user = await database_sync_to_async(User.objects.create_user)(
        email="ws@example.edu", password="correct-horse-battery"
    )
    comm = communicator(user)
    connected, _ = await comm.connect()
    assert connected is True

    assert await comm.receive_json_from() == {"type": "connected", "user": user.email}

    await comm.send_json_to({"hello": "world"})
    assert await comm.receive_json_from() == {
        "type": "echo",
        "payload": {"hello": "world"},
    }
    await comm.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_force_disconnect_closes_an_open_socket():
    user = await database_sync_to_async(User.objects.create_user)(
        email="revoked@example.edu", password="correct-horse-battery"
    )
    comm = communicator(user)
    connected, _ = await comm.connect()
    assert connected is True
    await comm.receive_json_from()  # the "connected" frame

    await database_sync_to_async(services.disconnect_sockets)(user.pk, "revoked")

    assert await comm.receive_json_from() == {"type": "disconnect", "reason": "revoked"}
    assert await comm.receive_output() == {"type": "websocket.close", "code": CLOSE_REVOKED}
    await comm.disconnect()
