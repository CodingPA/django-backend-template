"""
Deploy-time configuration checks for combinations that silently do the wrong
thing. Run with `manage.py check`.
"""

from urllib.parse import urlparse

from django.conf import settings
from django.core.checks import Warning, register


@register("auth")
def check_auth_configuration(app_configs, **kwargs):
    issues = []

    # allauth can only hide "this email already exists" by swallowing the
    # signup and sending an email instead. With verification off there is no
    # email to send, so it falls back to raising email_taken anyway and the
    # flag quietly does nothing.
    if (
        not settings.AUTH_DISCLOSE_ACCOUNT_EXISTENCE
        and settings.ACCOUNT_EMAIL_VERIFICATION != "mandatory"
    ):
        issues.append(
            Warning(
                "AUTH_DISCLOSE_ACCOUNT_EXISTENCE=False has no effect unless "
                "ACCOUNT_EMAIL_VERIFICATION='mandatory'.",
                hint=(
                    "Enumeration prevention works by responding to a duplicate "
                    "signup as though a verification email were sent. Without "
                    "mandatory verification allauth reports email_taken anyway. "
                    "Set ACCOUNT_EMAIL_VERIFICATION=mandatory and configure "
                    "EMAIL_BACKEND, or accept the disclosure."
                ),
                id="auth.W001",
            )
        )

    if settings.ACCOUNT_EMAIL_VERIFICATION != "none" and settings.EMAIL_BACKEND.endswith(
        "console.EmailBackend"
    ):
        issues.append(
            Warning(
                "Email verification is enabled but email goes to the console.",
                hint="Set EMAIL_BACKEND and the EMAIL_HOST_* variables.",
                id="auth.W002",
            )
        )

    google = settings.SOCIALACCOUNT_PROVIDERS.get("google", {}).get("APP", {})
    if not settings.DEBUG and not google.get("client_id"):
        issues.append(
            Warning(
                "Google login is installed but GOOGLE_CLIENT_ID is unset.",
                hint="Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET, or remove "
                "allauth.socialaccount.providers.google from INSTALLED_APPS.",
                id="auth.W003",
            )
        )

    if not settings.DEBUG and not settings.SESSION_COOKIE_DOMAIN:
        issues.append(
            Warning(
                "COOKIE_DOMAIN is unset, so the session cookie will not be sent "
                "to a frontend on a sibling subdomain.",
                hint="Set COOKIE_DOMAIN to the shared parent, e.g. '.example.com'.",
                id="auth.W004",
            )
        )

    # The WebSocket handshake Origin is the frontend's host, not this API's, so
    # a frontend missing from WEBSOCKET_ALLOWED_ORIGINS gets a silent 403 on
    # every socket while ordinary HTTP keeps working.
    frontend_host = urlparse(settings.FRONTEND_URL).hostname
    ws_hosts = {
        urlparse(origin if "//" in origin else f"//{origin}").hostname
        for origin in settings.WEBSOCKET_ALLOWED_ORIGINS
    }
    if frontend_host and "*" not in settings.WEBSOCKET_ALLOWED_ORIGINS:
        if frontend_host not in ws_hosts:
            issues.append(
                Warning(
                    f"FRONTEND_URL host '{frontend_host}' is not in "
                    "WEBSOCKET_ALLOWED_ORIGINS, so the frontend cannot open a "
                    "WebSocket.",
                    hint=(
                        "WebSocket origin checking uses the frontend's host, "
                        "not ALLOWED_HOSTS. Add it to CORS_ALLOWED_ORIGINS or "
                        "set WEBSOCKET_ALLOWED_ORIGINS explicitly."
                    ),
                    id="auth.W005",
                )
            )

    return issues
