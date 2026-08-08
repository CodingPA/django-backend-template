from django.urls import path

from apps.users import api

app_name = "users"

urlpatterns = [
    path("auth/access-code/", api.ValidateAccessCodeView.as_view(), name="access-code"),
    path("auth/email-status/", api.EmailStatusView.as_view(), name="email-status"),
    path(
        "auth/sessions/revoke-others/",
        api.RevokeOtherSessionsView.as_view(),
        name="revoke-other-sessions",
    ),
]
