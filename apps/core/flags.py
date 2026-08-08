"""
Feature flag accessors.

Call these instead of reading ``settings.SIGNUP_ENABLED`` directly. The backing
store is environment variables today; routing every read through here means it
can become a database singleton or a remote flag service later without touching
any call site.
"""

from django.conf import settings


def signup_enabled() -> bool:
    """Whether new accounts may be created at all, by any method."""
    return bool(getattr(settings, "SIGNUP_ENABLED", True))


def signup_requires_access_code() -> bool:
    """Whether a valid AccessCode must be presented before signup."""
    return bool(getattr(settings, "SIGNUP_REQUIRES_ACCESS_CODE", False))


def disclose_account_existence() -> bool:
    """
    Whether the API may tell an anonymous caller that an email is registered,
    and which authentication method it uses.

    True gives a much better error message ("this email uses Google, sign in
    with Google") at the cost of confirming account existence. False routes
    through allauth's enumeration-resistant flow instead.
    """
    return bool(getattr(settings, "AUTH_DISCLOSE_ACCOUNT_EXISTENCE", True))


def as_dict() -> dict:
    """Public flag payload served to the frontend at /api/config/."""
    return {
        "signup_enabled": signup_enabled(),
        "signup_requires_access_code": signup_requires_access_code(),
    }
