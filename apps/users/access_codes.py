"""
Access code validation, shared by the email and Google signup paths.

Google signups have no form to hang an ``access_code`` field on: the user
leaves for Google and comes back already authenticated. So the code is
validated up front and the result is stashed in the session, and both signup
paths read it from there. The email path may also pass the code inline on the
signup request, which is validated through the same function.
"""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from apps.core import flags
from apps.users.models import AccessCode

logger = logging.getLogger(__name__)

SESSION_KEY = "pending_access_code_id"

#: Marker on the request object, so a code is claimed at most once per signup.
_CONSUMED_ATTR = "_access_code_consumed"

INVALID_MESSAGE = _("That access code is not valid.")


def validate(code: str) -> AccessCode:
    """Return the usable AccessCode for ``code`` or raise ValidationError."""
    normalized = (code or "").strip().upper()
    if not normalized:
        raise ValidationError(INVALID_MESSAGE, code="access_code_invalid")
    try:
        access_code = AccessCode.objects.usable().get(code=normalized)
    except AccessCode.DoesNotExist as exc:
        # Deliberately identical for unknown, expired, exhausted and disabled
        # codes: distinguishing them would let a caller probe the code space.
        raise ValidationError(INVALID_MESSAGE, code="access_code_invalid") from exc
    return access_code


def stash(request: HttpRequest, access_code: AccessCode) -> None:
    request.session[SESSION_KEY] = access_code.pk


def get_stashed(request: HttpRequest) -> AccessCode | None:
    pk = request.session.get(SESSION_KEY)
    if not pk:
        return None
    access_code = AccessCode.objects.filter(pk=pk).usable().first()
    if access_code is None:
        # Went stale between validation and signup (revoked or used up).
        request.session.pop(SESSION_KEY, None)
    return access_code


def clear(request: HttpRequest) -> None:
    request.session.pop(SESSION_KEY, None)


def resolve(request: HttpRequest, inline_code: str | None = None) -> AccessCode | None:
    """
    Find the access code covering this signup: an inline one on the request
    body takes precedence, otherwise whatever was stashed earlier.
    """
    if inline_code:
        return validate(inline_code)
    return get_stashed(request)


def require(request: HttpRequest, inline_code: str | None = None) -> AccessCode | None:
    """
    Enforce the SIGNUP_REQUIRES_ACCESS_CODE flag. Returns the code to consume,
    or None when the flag is off. Raises ValidationError when one is needed
    and absent.
    """
    if not flags.signup_requires_access_code():
        return None
    access_code = resolve(request, inline_code)
    if access_code is None:
        raise ValidationError(
            _("An access code is required to sign up."),
            code="access_code_required",
        )
    return access_code


def consume(request: HttpRequest, access_code: AccessCode | None, user) -> None:
    """
    Claim one use of the code and forget it. Safe to call with None.

    Guarded per request because two owners can reach here for a single signup:
    ``SocialAccountAdapter.save_user`` and ``SignupExtraFieldsForm.signup``.
    allauth calls both on the social-signup-with-form path. A ``max_uses=1``
    code happens to self-limit, but a multi-use or unlimited one would be
    charged twice and log two redemptions.
    """
    if access_code is None or getattr(request, _CONSUMED_ATTR, False):
        return
    setattr(request, _CONSUMED_ATTR, True)
    if not access_code.consume(user=user):
        # Revoked or exhausted between validation and signup, most likely by a
        # concurrent signup taking the last use. The account is already created
        # at this point, so it stands -- but it has no redemption row, and that
        # divergence should not be invisible.
        logger.warning(
            "Access code %s went stale during signup for %s; account created "
            "without a recorded redemption.",
            access_code.code,
            getattr(user, "email", user),
        )
    clear(request)
