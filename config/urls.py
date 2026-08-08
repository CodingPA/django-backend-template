from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView

admin.site.site_header = f"{settings.PROJECT_NAME} admin"
admin.site.site_title = settings.PROJECT_NAME
admin.site.index_title = "Administration"

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    # allauth headless JSON API: /_allauth/browser/v1/...
    path("_allauth/", include("allauth.headless.urls")),
    # Under HEADLESS_ONLY this contributes only the OAuth provider routes.
    # Google's redirect URI is /accounts/google/login/callback/ and must be
    # registered verbatim in the Google Cloud console.
    path("accounts/", include("allauth.urls")),
    path("api/", include("apps.core.urls")),
    path("api/", include("apps.users.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularRedocView.as_view(url_name="schema"), name="docs"),
]
