"""
An access code must be claimed exactly once per signup.

Two things call `access_codes.consume`: `SocialAccountAdapter.save_user` and
`SignupExtraFieldsForm.signup`. On the social-signup-with-form path allauth
invokes both, so without a guard a `max_uses=1` code reaches `uses=2` and logs
two redemptions.
"""

import pytest
from allauth.core import context
from allauth.socialaccount.internal.flows import signup as social_signup_flow
from django.test import override_settings

from apps.users import access_codes
from apps.users.tests.conftest import make_sociallogin

pytestmark = pytest.mark.django_db


@override_settings(SIGNUP_REQUIRES_ACCESS_CODE=True)
def test_google_auto_signup_consumes_the_code_once(social_request, access_code):
    access_codes.stash(social_request, access_code)
    social_request.session.save()

    with context.request_context(social_request):
        social_signup_flow.process_signup(social_request, make_sociallogin("newcomer@example.edu"))

    access_code.refresh_from_db()
    assert access_code.uses == 1
    assert access_code.redemptions.count() == 1


@override_settings(SIGNUP_REQUIRES_ACCESS_CODE=True)
def test_consume_is_idempotent_within_one_request(social_request, access_code, django_user_model):
    """
    Guards the path where both the adapter and the form claim the code.

    A max_uses=1 code self-limits, so this uses a multi-use code -- that is
    where a double claim actually over-counts.
    """
    access_code.max_uses = 5
    access_code.save()
    user = django_user_model.objects.create_user(email="dup@example.edu")

    access_codes.consume(social_request, access_code, user)
    access_codes.consume(social_request, access_code, user)

    access_code.refresh_from_db()
    assert access_code.uses == 1
    assert access_code.redemptions.count() == 1


@override_settings(SIGNUP_REQUIRES_ACCESS_CODE=True)
def test_unlimited_code_is_also_claimed_once_per_request(
    social_request, access_code, django_user_model
):
    access_code.max_uses = 0  # unlimited
    access_code.save()
    user = django_user_model.objects.create_user(email="unlimited@example.edu")

    access_codes.consume(social_request, access_code, user)
    access_codes.consume(social_request, access_code, user)

    access_code.refresh_from_db()
    assert access_code.uses == 1


@override_settings(SIGNUP_REQUIRES_ACCESS_CODE=True)
def test_separate_requests_each_consume(access_code, rf, client, django_user_model):
    """The guard is per request, not global -- a multi-use code still counts up."""
    access_code.max_uses = 5
    access_code.save()

    for i in range(3):
        request = rf.post("/")
        request.session = client.session
        user = django_user_model.objects.create_user(email=f"u{i}@example.edu")
        access_codes.consume(request, access_code, user)

    access_code.refresh_from_db()
    assert access_code.uses == 3
