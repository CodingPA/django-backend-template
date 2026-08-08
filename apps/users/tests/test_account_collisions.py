"""
One email address, one authentication method.

A Google login for an address that already has a password account must be
refused rather than auto-linked, and the refusal must name the method the
account actually uses so the frontend can point the user at the right door.
"""

import json

import pytest
from allauth.core import context
from django.core.exceptions import ValidationError
from django.test import override_settings

from apps.users.adapters import SocialAccountAdapter, describe_login_method
from apps.users.tests.conftest import (
    EMAIL_STATUS_URL,
    SIGNUP_URL,
    error_codes,
    make_sociallogin,
)


def social_login_attempt(rf, email, process="login"):
    request = rf.post("/")
    request.session = {}
    adapter = SocialAccountAdapter()
    with context.request_context(request):
        adapter.pre_social_login(request, make_sociallogin(email, process=process))


# -- Google login hitting an existing account ------------------------------


@pytest.mark.django_db
def test_google_login_on_password_account_is_refused(rf, password_user):
    with pytest.raises(ValidationError) as exc:
        social_login_attempt(rf, password_user.email)
    assert exc.value.code == "email_taken_by_password"


@pytest.mark.django_db
def test_google_login_names_the_existing_provider(rf, google_user):
    """
    A second, unlinked Google identity claiming an address that already has a
    Google-backed account. Refused, and the provider is named.
    """
    with pytest.raises(ValidationError) as exc:
        social_login_attempt(rf, google_user.email)
    assert exc.value.code == "email_taken_by_provider"
    assert "Google" in exc.value.messages[0]


@pytest.mark.django_db
def test_connecting_a_provider_while_signed_in_is_not_a_collision(rf, password_user):
    """The connect flow is an authenticated action, so it must not be blocked."""
    social_login_attempt(rf, password_user.email, process="connect")


@pytest.mark.django_db
def test_unknown_email_is_not_a_collision(rf):
    social_login_attempt(rf, "nobody@example.edu")


# -- Email signup hitting an existing account ------------------------------


@pytest.mark.django_db
def test_email_signup_on_existing_account_is_refused(client, google_user):
    response = client.post(
        SIGNUP_URL,
        data=json.dumps({"email": google_user.email, "password": "correct-horse-battery"}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "email_taken" in error_codes(response)


# -- describe_login_method -------------------------------------------------


@pytest.mark.django_db
def test_describe_login_method(password_user, google_user):
    assert describe_login_method(password_user) == "password"
    assert describe_login_method(google_user) == "google"


# -- AUTH_DISCLOSE_ACCOUNT_EXISTENCE ---------------------------------------


@pytest.mark.django_db
@override_settings(AUTH_DISCLOSE_ACCOUNT_EXISTENCE=True)
def test_email_status_reports_method_when_disclosure_is_on(client, google_user):
    response = client.get(EMAIL_STATUS_URL, {"email": google_user.email})
    assert response.status_code == 200
    assert response.json() == {"exists": True, "method": "google"}


@pytest.mark.django_db
@override_settings(AUTH_DISCLOSE_ACCOUNT_EXISTENCE=True)
def test_email_status_reports_unknown_address(client):
    response = client.get(EMAIL_STATUS_URL, {"email": "nobody@example.edu"})
    assert response.json() == {"exists": False, "method": None}


@pytest.mark.django_db
@override_settings(AUTH_DISCLOSE_ACCOUNT_EXISTENCE=False)
def test_email_status_is_gone_when_disclosure_is_off(client, google_user):
    assert client.get(EMAIL_STATUS_URL, {"email": google_user.email}).status_code == 404


@pytest.mark.django_db
@override_settings(AUTH_DISCLOSE_ACCOUNT_EXISTENCE=False)
def test_google_collision_is_generic_when_disclosure_is_off(rf, password_user):
    with pytest.raises(ValidationError) as exc:
        social_login_attempt(rf, password_user.email)
    assert exc.value.code == "email_taken"
    assert "password" not in exc.value.messages[0].lower()
