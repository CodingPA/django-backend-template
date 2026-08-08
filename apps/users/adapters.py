"""
allauth adapters.

There are three distinct ways an account can come into existence, and the
signup feature flags have to close all three or they are not actually closed:

    1. Email + password signup      -> AccountAdapter.is_open_for_signup
                                       + SignupExtraFieldsForm (access code)
    2. Google login, new user       -> SocialAccountAdapter.is_open_for_signup
                                       + pre_social_login (access code)
    3. Google login, email already
       belongs to an account        -> pre_social_login (rejected, not linked)

Case 3 is a linking decision rather than a signup, which is why it needs its
own handling: without it, a "signup disabled" deployment would still let
someone in through an existing address.
"""

from __future__ import annotations

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.utils import filter_users_by_email
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialAccount, SocialLogin
from allauth.socialaccount.providers.base import AuthProcess
from django.core.exceptions import ValidationError
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from apps.core import flags
from apps.core.tasks import send_email
from apps.users import access_codes


def describe_login_method(user) -> str | None:
    """
    How does this account authenticate? Returns a provider id ("google"), the
    string "password", or None if neither is usable.
    """
    provider = SocialAccount.objects.filter(user=user).values_list("provider", flat=True).first()
    if provider:
        return provider
    if user.has_usable_password():
        return "password"
    return None


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request: HttpRequest) -> bool:
        """
        Gates the email/password signup endpoint, and is also reported by
        allauth's /_allauth/browser/v1/config so the frontend can hide the
        signup form. Intentionally reflects only SIGNUP_ENABLED: needing an
        access code is a separate condition, surfaced as its own error.
        """
        return flags.signup_enabled()

    def send_mail(self, template_prefix, email, context) -> None:
        """
        Hand verification and password-reset mail to Celery so a slow SMTP
        server cannot stall the request that triggered it. Rendering still
        happens here, in request context, because the templates need it.
        """
        message = self.render_mail(template_prefix, email, context)
        html = next(
            (
                content
                for content, mimetype in getattr(message, "alternatives", [])
                if mimetype == "text/html"
            ),
            None,
        )
        send_email.delay(message.subject, message.body, list(message.to), html)


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request: HttpRequest, sociallogin: SocialLogin) -> bool:
        """
        Closing this is what stops "sign in with Google" quietly creating
        accounts while email signup is switched off. Surfaces through allauth
        as ?error=signup_closed on the frontend callback URL.
        """
        return flags.signup_enabled()

    def pre_social_login(self, request: HttpRequest, sociallogin: SocialLogin) -> None:
        """
        Runs after Google has authenticated the user but before allauth acts on
        it. ValidationErrors raised here become
        ?error=<code>&error_process=login on the frontend callback URL -- not
        JSON, because this leg of the flow is a browser redirect.
        """
        # An already-linked Google account: an ordinary login, nothing to check.
        if sociallogin.is_existing:
            return

        # Connecting a provider to an account that is already signed in is an
        # authenticated action, not a signup.
        if sociallogin.state.get("process") == AuthProcess.CONNECT:
            return

        email = self._email_of(sociallogin)
        if email:
            existing = filter_users_by_email(email)
            if existing:
                self._reject_collision(existing[0])

        # A genuinely new account. SIGNUP_ENABLED is handled by
        # is_open_for_signup; the access code is checked here so that a missing
        # code reports itself distinctly instead of looking like closed signup.
        access_codes.require(request)

    def save_user(self, request: HttpRequest, sociallogin: SocialLogin, form=None):
        user = super().save_user(request, sociallogin, form)
        # Re-read rather than carrying state from pre_social_login: allauth
        # instantiates a fresh adapter per call, so instance attributes set
        # there are gone by now.
        if flags.signup_requires_access_code():
            access_codes.consume(request, access_codes.get_stashed(request), user)
        return user

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _email_of(sociallogin: SocialLogin) -> str | None:
        if sociallogin.email_addresses:
            return sociallogin.email_addresses[0].email
        return getattr(sociallogin.user, "email", None) or None

    @staticmethod
    def _reject_collision(user) -> None:
        """
        One email address, one authentication method. Auto-linking a social
        login to an existing local account is an account-takeover vector for
        any provider that does not verify email ownership, so the login is
        refused and the frontend is told which door to send the user to.
        """
        if not flags.disclose_account_existence():
            raise ValidationError(
                _("This account cannot be used to sign in."),
                code="email_taken",
            )

        method = describe_login_method(user)
        if method == "password":
            raise ValidationError(
                _("An account with this email already exists. Sign in with your password."),
                code="email_taken_by_password",
            )
        if method is None:
            # The account exists but has no way in -- no usable password and no
            # linked provider, e.g. its SocialAccount row was deleted. Naming a
            # provider that is not there would strand the user in a loop.
            raise ValidationError(
                _("An account with this email exists but has no sign-in method."),
                code="email_taken_no_method",
            )
        raise ValidationError(
            _("An account with this email already exists. Sign in with %(provider)s.")
            % {"provider": method.title()},
            code="email_taken_by_provider",
        )
