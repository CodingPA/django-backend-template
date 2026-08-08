import pytest
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage

from apps.users.models import AccessCode

User = get_user_model()

SIGNUP_URL = "/_allauth/browser/v1/auth/signup"
LOGIN_URL = "/_allauth/browser/v1/auth/login"
SESSION_URL = "/_allauth/browser/v1/auth/session"
ACCESS_CODE_URL = "/api/auth/access-code/"
EMAIL_STATUS_URL = "/api/auth/email-status/"


@pytest.fixture
def password_user(db):
    user = User.objects.create_user(email="local@example.edu", password="correct-horse-battery")
    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    return user


@pytest.fixture
def google_user(db):
    user = User.objects.create_user(email="social@example.edu")
    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    SocialAccount.objects.create(user=user, provider="google", uid="google-uid-1")
    return user


@pytest.fixture
def access_code(db):
    return AccessCode.objects.create(code="LETMEIN01", max_uses=1)


@pytest.fixture
def social_request(rf, client):
    """
    A request carrying everything allauth's login pipeline touches. The bare
    RequestFactory object has no session, user or message storage, all of which
    normally come from middleware.
    """
    request = rf.post("/")
    request.session = client.session
    request.user = AnonymousUser()
    request._messages = FallbackStorage(request)
    return request


def make_sociallogin(email: str, uid: str = "new-uid", process: str = "login"):
    """An unsaved Google login, as allauth builds it after the OAuth callback."""
    sociallogin = SocialLogin(
        user=User(email=email),
        account=SocialAccount(provider="google", uid=uid),
        email_addresses=[EmailAddress(email=email, verified=True, primary=True)],
    )
    sociallogin.state = {"process": process, "next": "/"}
    return sociallogin


def error_codes(response) -> set[str]:
    """Collect the `code` values out of an allauth headless error payload."""
    return {error.get("code") for error in response.json().get("errors", [])}
