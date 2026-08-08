"""
Revocation is the reason this template uses session cookies rather than JWTs,
so it is worth proving that a revoked session is genuinely dead.
"""

from importlib import import_module

import pytest
from allauth.usersessions.models import UserSession
from django.conf import settings

from apps.users import services


def session_store():
    return import_module(settings.SESSION_ENGINE).SessionStore


def make_session(user, ip="127.0.0.1", user_agent="test"):
    store = session_store()()
    store["_auth_user_id"] = str(user.pk)
    store.create()
    UserSession.objects.create(
        user=user, session_key=store.session_key, ip=ip, user_agent=user_agent
    )
    return store


@pytest.mark.django_db
def test_invalidate_all_sessions_deletes_the_underlying_session(password_user):
    store = make_session(password_user)
    assert session_store()().exists(store.session_key)

    assert services.invalidate_all_sessions(password_user) == 1

    assert not session_store()().exists(store.session_key)
    assert UserSession.objects.filter(user=password_user).count() == 0


@pytest.mark.django_db
def test_invalidate_all_sessions_can_keep_the_current_device(password_user):
    keep = make_session(password_user, user_agent="this device")
    drop = make_session(password_user, user_agent="other device")

    ended = services.invalidate_all_sessions(password_user, except_session_key=keep.session_key)

    assert ended == 1
    assert session_store()().exists(keep.session_key)
    assert not session_store()().exists(drop.session_key)


@pytest.mark.django_db
def test_end_session_targets_one_device(password_user):
    keep = make_session(password_user)
    drop = make_session(password_user)

    assert services.end_session(password_user, drop.session_key) is True
    assert services.end_session(password_user, "not-a-real-key") is False
    assert session_store()().exists(keep.session_key)
    assert not session_store()().exists(drop.session_key)


@pytest.mark.django_db
def test_ban_user_deactivates_and_clears_sessions(password_user):
    store = make_session(password_user)

    services.ban_user(password_user)

    password_user.refresh_from_db()
    assert password_user.is_active is False
    assert not session_store()().exists(store.session_key)


@pytest.mark.django_db
def test_banned_user_cannot_log_in(client, password_user):
    services.ban_user(password_user)
    response = client.post(
        "/_allauth/browser/v1/auth/login",
        data='{"email": "local@example.edu", "password": "correct-horse-battery"}',
        content_type="application/json",
    )
    assert response.status_code == 401
    assert client.get("/_allauth/browser/v1/auth/session").status_code == 401


@pytest.mark.django_db
def test_rotate_session_auth_hash_leaves_no_usable_password(password_user):
    services.rotate_session_auth_hash(password_user)
    password_user.refresh_from_db()
    assert password_user.has_usable_password() is False


@pytest.mark.django_db
def test_revoke_others_endpoint_keeps_the_calling_session(client, password_user):
    other = make_session(password_user)
    client.force_login(password_user)

    response = client.post("/api/auth/sessions/revoke-others/")

    assert response.status_code == 200
    assert response.json()["ended"] == 1
    assert not session_store()().exists(other.session_key)
    # The caller is still authenticated.
    assert client.get("/api/config/").status_code == 200
