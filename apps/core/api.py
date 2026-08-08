from django.conf import settings
from django.db import connection
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import flags


class ConfigView(APIView):
    """
    Public runtime configuration for the frontend: project identity plus the
    feature flags it needs in order to render the right auth screens.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        responses=inline_serializer(
            "Config",
            {
                "project_name": serializers.CharField(),
                "project_slug": serializers.CharField(),
                "signup_enabled": serializers.BooleanField(),
                "signup_requires_access_code": serializers.BooleanField(),
                "social_providers": serializers.ListField(child=serializers.CharField()),
            },
        )
    )
    def get(self, request):
        providers = [
            provider
            for provider, config in settings.SOCIALACCOUNT_PROVIDERS.items()
            if config.get("APP", {}).get("client_id")
        ]
        return Response(
            {
                "project_name": settings.PROJECT_NAME,
                "project_slug": settings.PROJECT_SLUG,
                "social_providers": providers,
                **flags.as_dict(),
            }
        )


class HealthView(APIView):
    """Liveness/readiness probe. Checks the database; never cached."""

    permission_classes = [AllowAny]

    @extend_schema(
        responses=inline_serializer(
            "Health",
            {"status": serializers.CharField(), "database": serializers.CharField()},
        )
    )
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            database = "ok"
        except Exception:  # noqa: BLE001 - the probe must not raise
            database = "error"
        healthy = database == "ok"
        return Response(
            {"status": "ok" if healthy else "degraded", "database": database},
            status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        )
