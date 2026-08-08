"""
Session revocation.

This is the payoff of using session cookies rather than JWTs: a session is a
server-side record, so it can actually be taken back. A JWT stays valid until
it expires unless you build a blocklist -- which is a per-request lookup, i.e.
a session with extra steps.

Three levers, from blunt to precise:

    ban_user()               -> is_active=False, rejected on the next request
    invalidate_all_sessions()-> rotates the session auth hash, drops every
                                session, account stays usable
    end_session()            -> kills one device

All of them also close any WebSocket the user has open, which would otherwise
keep streaming: sockets authenticate once, at the handshake.
"""

from __future__ import annotations

from allauth.usersessions.models import UserSession
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model

User = get_user_model()


def user_control_group(user_id) -> str:
    """Channel group every one of a user's sockets subscribes to."""
    return f"user.{user_id}.control"


def disconnect_sockets(user_id, reason: str = "revoked") -> None:
    """Tell every live socket for this user to close."""
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        user_control_group(user_id),
        {"type": "force.disconnect", "reason": reason},
    )


def invalidate_all_sessions(user, *, except_session_key: str | None = None) -> int:
    """
    End every session for this user. Returns how many were ended.

    Django stores an HMAC of the password in each session and re-checks it on
    every request, so rotating it would also do the job -- but that logs the
    user out of a password change they just made, and gives no count. Deleting
    the tracked sessions is more precise.
    """
    sessions = UserSession.objects.filter(user=user)
    if except_session_key:
        sessions = sessions.exclude(session_key=except_session_key)
    count = 0
    for session in sessions:
        session.end()
        count += 1
    disconnect_sockets(user.pk)
    return count


def end_session(user, session_key: str) -> bool:
    """End one specific device's session."""
    session = UserSession.objects.filter(user=user, session_key=session_key).first()
    if session is None:
        return False
    session.end()
    disconnect_sockets(user.pk, reason="session_ended")
    return True


def ban_user(user) -> None:
    """
    Hard kill switch. An inactive user is rejected by the auth backend on the
    next request, so this invalidates every session everywhere at once,
    including ones not tracked by UserSession.
    """
    user.is_active = False
    user.save(update_fields=["is_active"])
    invalidate_all_sessions(user)
    disconnect_sockets(user.pk, reason="account_disabled")


def rotate_session_auth_hash(user) -> None:
    """
    Nuclear option that does not depend on session tracking: give the user a
    new unusable password so the stored session auth hash stops matching.
    Works for Google-only accounts too, since set_unusable_password() writes a
    fresh random value each time. Destroys any existing password.
    """
    user.set_unusable_password()
    user.save(update_fields=["password"])
    disconnect_sockets(user.pk, reason="credentials_rotated")
