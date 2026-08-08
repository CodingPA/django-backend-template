"""
Signup form extension.

``ACCOUNT_SIGNUP_FORM_CLASS`` points here. allauth injects this class as a base
of its own signup form, which means it also applies to the headless JSON signup
endpoint and its ``access_code`` field shows up in the generated OpenAPI spec.
"""

from __future__ import annotations

from allauth.core import context
from django import forms

from apps.core import flags
from apps.users import access_codes


class SignupExtraFieldsForm(forms.Form):
    access_code = forms.CharField(required=False, max_length=64)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not flags.signup_requires_access_code():
            del self.fields["access_code"]

    def clean(self):
        cleaned = super().clean()
        try:
            self._access_code = access_codes.require(context.request, cleaned.get("access_code"))
        except forms.ValidationError as exc:
            # Attached to the field so the headless layer emits
            # {"code": "access_code_required", "param": "access_code"}.
            self.add_error("access_code", exc)
        return cleaned

    def signup(self, request, user):
        """Called by allauth once the user row exists."""
        access_codes.consume(request, getattr(self, "_access_code", None), user)
