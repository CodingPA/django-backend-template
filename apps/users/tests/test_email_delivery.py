"""
Verification and reset mail is rendered in the request and delivered by Celery
(`AccountAdapter.send_mail` -> `core.send_email`, eager in tests). Nothing else
in the suite exercises that chain, because the shipped configuration sends no
mail at all -- so a break in it would first show up as a silent failure on the
first production password reset.
"""

import json

import pytest
from django.conf import settings
from django.core import mail
from django.test import override_settings

from apps.users.tests.conftest import SIGNUP_URL

pytestmark = pytest.mark.django_db

NEW = {"email": "verifyme@example.com", "password": "correct-horse-battery"}

# Note: do not add pytest-django's `settings` fixture to these tests. It unwinds
# the override_settings decorator, and the mail simply stops being sent.
verification_on = override_settings(
    ACCOUNT_EMAIL_VERIFICATION="mandatory",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)


def signup(client):
    return client.post(SIGNUP_URL, data=json.dumps(NEW), content_type="application/json")


@verification_on
def test_signup_sends_a_verification_email_through_celery(client):
    mail.outbox.clear()

    # 401: the account exists but the login is parked at the email-verification
    # stage, which is what mandatory verification is supposed to do.
    assert signup(client).status_code == 401

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [NEW["email"]]
    assert mail.outbox[0].subject


@verification_on
def test_verification_link_points_at_the_frontend(client):
    """The confirmation URL must land on the Next.js app, not a Django page."""
    mail.outbox.clear()
    signup(client)

    assert settings.FRONTEND_URL in mail.outbox[0].body


@verification_on
def test_password_reset_sends_mail(client, password_user):
    mail.outbox.clear()

    response = client.post(
        "/_allauth/browser/v1/auth/password/request",
        data=json.dumps({"email": password_user.email}),
        content_type="application/json",
    )

    assert response.status_code in (200, 401), response.content
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [password_user.email]


@verification_on
def test_subject_carries_the_project_name(client):
    """PROJECT_NAME reaches outbound mail, so a clone is not sending as the template."""
    mail.outbox.clear()
    signup(client)

    assert settings.PROJECT_NAME in mail.outbox[0].subject
