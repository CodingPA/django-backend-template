"""
The small amount of auth surface allauth does not already cover.

Everything else -- login, signup, logout, password reset, email verification,
Google redirect, per-device session list -- lives under /_allauth/browser/v1/.
"""

from __future__ import annotations

from allauth.account.utils import filter_users_by_email
from django.core.exceptions import ValidationError
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import flags
from apps.users import access_codes, services
from apps.users.adapters import describe_login_method


class AccessCodeInputSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=64)


class AccessCodeResultSerializer(serializers.Serializer):
    valid = serializers.BooleanField()


class ValidateAccessCodeView(APIView):
    """
    Validate an access code and remember it for the signup that follows.

    The Google path needs this: the user leaves for Google and returns already
    authenticated, with no form to carry the code on. Validating up front and
    stashing the result in the session means one mechanism covers both signup
    paths. The email path may skip this and pass ``access_code`` inline to the
    allauth signup endpoint instead.
    """

    permission_classes = [AllowAny]
    throttle_scope = "access_code"

    @extend_schema(
        request=AccessCodeInputSerializer,
        responses={
            200: AccessCodeResultSerializer,
            400: OpenApiResponse(description="Code is invalid, expired or used up."),
            409: OpenApiResponse(description="Signup does not require an access code."),
        },
    )
    def post(self, request):
        if not flags.signup_requires_access_code():
            return Response(
                {"detail": "Access codes are not required.", "code": "not_required"},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = AccessCodeInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            access_code = access_codes.validate(serializer.validated_data["code"])
        except ValidationError as exc:
            return Response(
                {"detail": exc.messages[0], "code": "access_code_invalid"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        access_codes.stash(request, access_code)
        return Response({"valid": True})


class EmailStatusSerializer(serializers.Serializer):
    exists = serializers.BooleanField()
    method = serializers.CharField(allow_null=True)


class EmailStatusView(APIView):
    """
    Report whether an email is already registered and how it signs in, so the
    frontend can say "this address uses Google" before the user fills in a
    password.

    This is the only endpoint that intentionally discloses account existence.
    It returns 404 when AUTH_DISCLOSE_ACCOUNT_EXISTENCE is off, which keeps the
    whole enumeration surface behind one flag.
    """

    permission_classes = [AllowAny]
    throttle_scope = "email_status"

    @extend_schema(
        parameters=[OpenApiParameter("email", str, required=True)],
        responses={
            200: EmailStatusSerializer,
            404: OpenApiResponse(description="Disabled by configuration."),
        },
    )
    def get(self, request):
        if not flags.disclose_account_existence():
            return Response(status=status.HTTP_404_NOT_FOUND)
        email = (request.query_params.get("email") or "").strip()
        if not email:
            return Response({"detail": "email is required."}, status=status.HTTP_400_BAD_REQUEST)
        users = filter_users_by_email(email)
        if not users:
            return Response({"exists": False, "method": None})
        return Response({"exists": True, "method": describe_login_method(users[0])})


class RevokeOtherSessionsView(APIView):
    """Sign out of every other device, keeping the current one."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={200: OpenApiResponse(description="Count of sessions ended.")},
    )
    def post(self, request):
        ended = services.invalidate_all_sessions(
            request.user, except_session_key=request.session.session_key
        )
        return Response({"ended": ended})
