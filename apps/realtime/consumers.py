"""
WebSocket consumers.

Authentication is the same session cookie the REST API uses -- Channels'
AuthMiddlewareStack reads it off the handshake, so there is no token plumbing.

The catch is that a socket authenticates *once*, at connect. Revoking a session
does not by itself close a connection that is already open, so every consumer
here joins a per-user control group and closes when told to. There is also a
periodic re-check as a backstop for a missed message.
"""

from __future__ import annotations

import asyncio
import contextlib

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings

from apps.users.services import user_control_group

# How often an open socket re-confirms its user is still allowed to be here.
REVALIDATE_INTERVAL_SECONDS = getattr(settings, "WS_REVALIDATE_INTERVAL_SECONDS", 60)

CLOSE_UNAUTHENTICATED = 4401
CLOSE_REVOKED = 4403


class AuthenticatedConsumer(AsyncJsonWebsocketConsumer):
    """
    Base class for sockets that require a signed-in user. Subclass it and
    implement ``receive_json``; ``self.user`` is available throughout.
    """

    #: Extra channel groups to join on connect.
    groups_for_user: tuple[str, ...] = ()

    async def connect(self):
        self.user = self.scope.get("user")
        if self.user is None or not self.user.is_authenticated:
            await self.close(code=CLOSE_UNAUTHENTICATED)
            return

        self.control_group = user_control_group(self.user.pk)
        await self.channel_layer.group_add(self.control_group, self.channel_name)
        for group in self.groups_for_user:
            await self.channel_layer.group_add(group, self.channel_name)

        await self.accept()
        self._revalidator = asyncio.create_task(self._revalidate_loop())

    async def disconnect(self, code):
        task = getattr(self, "_revalidator", None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if getattr(self, "control_group", None):
            await self.channel_layer.group_discard(self.control_group, self.channel_name)
            for group in self.groups_for_user:
                await self.channel_layer.group_discard(group, self.channel_name)

    async def force_disconnect(self, event):
        """Handler for the group message sent by apps.users.services."""
        await self.send_json({"type": "disconnect", "reason": event.get("reason", "revoked")})
        await self.close(code=CLOSE_REVOKED)

    async def _revalidate_loop(self):
        """Backstop in case a force_disconnect message is never delivered."""
        while True:
            await asyncio.sleep(REVALIDATE_INTERVAL_SECONDS)
            if not await self._still_valid():
                await self.close(code=CLOSE_REVOKED)
                return

    @database_sync_to_async
    def _still_valid(self) -> bool:
        from django.contrib.auth import get_user_model

        return get_user_model().objects.filter(pk=self.user.pk, is_active=True).exists()


class EchoConsumer(AuthenticatedConsumer):
    """
    Placeholder so the WebSocket stack is verifiable end to end on a fresh
    clone. Replace it with something real; keep the base class.
    """

    async def connect(self):
        await super().connect()
        if self.user and self.user.is_authenticated:
            await self.send_json({"type": "connected", "user": str(self.user)})

    async def receive_json(self, content, **kwargs):
        await self.send_json({"type": "echo", "payload": content})
