"""
The signup feature flags must close every path into the user table, not just
the email form. These tests exist because "signup disabled" that still lets
people in through Google is the failure mode this template is most likely to
ship with.
"""

import json

import pytest
from allauth.core import context
from allauth.core.exceptions import SignupClosedException
from allauth.socialaccount.internal.flows import signup as social_signup_flow
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import override_settings

from apps.users.adapters import SocialAccountAdapter
from apps.users.models import AccessCode
from apps.users.tests.conftest import (
    ACCESS_CODE_URL,
    SIGNUP_URL,
    error_codes,
    make_sociallogin,
)

User = get_user_model()

NEW = {"email": "newcomer@example.edu", "password": "correct-horse-battery"}


def post_json(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type="application/json")


# -- SIGNUP_ENABLED --------------------------------------------------------


@pytest.mark.django_db
@override_settings(SIGNUP_ENABLED=True)
def test_email_signup_allowed_when_enabled(client):
    response = post_json(client, SIGNUP_URL, NEW)
    assert response.status_code == 200, response.content
    assert User.objects.filter(email=NEW["email"]).exists()


@pytest.mark.django_db
@override_settings(SIGNUP_ENABLED=False)
def test_email_signup_blocked_when_disabled(client):
    response = post_json(client, SIGNUP_URL, NEW)
    assert response.status_code == 403
    assert not User.objects.filter(email=NEW["email"]).exists()


@pytest.mark.django_db
@override_settings(SIGNUP_ENABLED=False)
def test_google_signup_blocked_when_disabled(social_request):
    """
    The bypass this test guards: Google quietly creating accounts while signup
    is off. Driven through allauth's real social signup flow rather than just
    asserting the predicate, so it fails if the flow stops consulting it.
    """
    request = social_request
    with context.request_context(request):
        with pytest.raises(SignupClosedException):
            social_signup_flow.process_signup(request, make_sociallogin("newcomer@example.edu"))
    assert not User.objects.filter(email="newcomer@example.edu").exists()


@pytest.mark.django_db
@override_settings(SIGNUP_ENABLED=True)
def test_google_signup_allowed_when_enabled(social_request):
    request = social_request
    with context.request_context(request):
        social_signup_flow.process_signup(request, make_sociallogin("newcomer@example.edu"))
    assert User.objects.filter(email="newcomer@example.edu").exists()


@pytest.mark.django_db
@override_settings(SIGNUP_ENABLED=False)
def test_config_endpoint_reports_signup_closed(client):
    body = client.get("/api/config/").json()
    assert body["signup_enabled"] is False


# -- SIGNUP_REQUIRES_ACCESS_CODE -------------------------------------------


@pytest.mark.django_db
@override_settings(SIGNUP_REQUIRES_ACCESS_CODE=True)
def test_email_signup_rejected_without_code(client):
    response = post_json(client, SIGNUP_URL, NEW)
    assert response.status_code == 400
    assert "access_code_required" in error_codes(response)
    assert not User.objects.filter(email=NEW["email"]).exists()


@pytest.mark.django_db
@override_settings(SIGNUP_REQUIRES_ACCESS_CODE=True)
def test_email_signup_rejected_with_bad_code(client):
    response = post_json(client, SIGNUP_URL, {**NEW, "access_code": "NOPE"})
    assert response.status_code == 400
    assert "access_code_invalid" in error_codes(response)


@pytest.mark.django_db
@override_settings(SIGNUP_REQUIRES_ACCESS_CODE=True)
def test_email_signup_accepts_inline_code_and_consumes_it(client, access_code):
    response = post_json(client, SIGNUP_URL, {**NEW, "access_code": access_code.code})
    assert response.status_code == 200, response.content
    access_code.refresh_from_db()
    assert access_code.uses == 1
    assert access_code.redemptions.count() == 1


@pytest.mark.django_db
@override_settings(SIGNUP_REQUIRES_ACCESS_CODE=True)
def test_preflight_endpoint_stashes_code_for_later_signup(client, access_code):
    """The path Google has to use, since it cannot carry a form field."""
    preflight = post_json(client, ACCESS_CODE_URL, {"code": access_code.code})
    assert preflight.status_code == 200
    assert preflight.json() == {"valid": True}

    # Same session, no code in the body this time.
    response = post_json(client, SIGNUP_URL, NEW)
    assert response.status_code == 200, response.content
    access_code.refresh_from_db()
    assert access_code.uses == 1


@pytest.mark.django_db
@override_settings(SIGNUP_REQUIRES_ACCESS_CODE=True)
def test_google_signup_rejected_without_code(social_request):
    adapter = SocialAccountAdapter()
    with context.request_context(social_request):
        with pytest.raises(ValidationError) as exc:
            adapter.pre_social_login(social_request, make_sociallogin("newcomer@example.edu"))
    assert exc.value.code == "access_code_required"


@pytest.mark.django_db
@override_settings(SIGNUP_REQUIRES_ACCESS_CODE=True)
def test_google_signup_accepts_stashed_code(rf, client, access_code):
    post_json(client, ACCESS_CODE_URL, {"code": access_code.code})
    request = rf.post("/")
    request.session = client.session
    adapter = SocialAccountAdapter()
    with context.request_context(request):
        adapter.pre_social_login(request, make_sociallogin("newcomer@example.edu"))


@pytest.mark.django_db
@override_settings(SIGNUP_REQUIRES_ACCESS_CODE=True)
def test_exhausted_code_is_rejected(client):
    code = AccessCode.objects.create(code="ONEONLY01", max_uses=1, uses=1)
    response = post_json(client, ACCESS_CODE_URL, {"code": code.code})
    assert response.status_code == 400


@pytest.mark.django_db
@override_settings(SIGNUP_REQUIRES_ACCESS_CODE=True)
def test_inactive_code_is_rejected(client):
    code = AccessCode.objects.create(code="REVOKED01", is_active=False)
    response = post_json(client, ACCESS_CODE_URL, {"code": code.code})
    assert response.status_code == 400


@pytest.mark.django_db
@override_settings(SIGNUP_REQUIRES_ACCESS_CODE=False)
def test_signup_needs_no_code_when_flag_is_off(client):
    response = post_json(client, SIGNUP_URL, NEW)
    assert response.status_code == 200, response.content
