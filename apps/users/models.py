from __future__ import annotations

import secrets

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    """Manager for a User keyed on email instead of username."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra):
        if not email:
            raise ValueError("Users must have an email address.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    """
    Email is the identifier; there is no username field.

    This model must exist before the first migration is generated. Swapping
    AUTH_USER_MODEL on a populated database is painful, which is why it is here
    from the start even though it adds no fields beyond the base.
    """

    username = None  # type: ignore[assignment]
    email = models.EmailField(_("email address"), unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def __str__(self) -> str:
        return self.email


class AccessCodeQuerySet(models.QuerySet):
    def usable(self):
        now = timezone.now()
        return self.filter(
            models.Q(is_active=True),
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now),
        ).filter(models.Q(max_uses=0) | models.Q(uses__lt=models.F("max_uses")))


class AccessCode(models.Model):
    """
    An invite code gating signup when SIGNUP_REQUIRES_ACCESS_CODE is on.

    A model rather than a single shared secret in the environment, so codes can
    be revoked, expired, counted, and audited individually.
    """

    code = models.CharField(max_length=64, unique=True, db_index=True)
    label = models.CharField(
        max_length=200, blank=True, help_text=_("Who or what this code was issued for.")
    )
    max_uses = models.PositiveIntegerField(default=1, help_text=_("0 means unlimited."))
    uses = models.PositiveIntegerField(default=0, editable=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_access_codes",
    )

    objects = AccessCodeQuerySet.as_manager()

    class Meta:
        verbose_name = _("access code")
        verbose_name_plural = _("access codes")
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.code

    @staticmethod
    def generate_code(length: int = 10) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no easily confused glyphs
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @property
    def is_exhausted(self) -> bool:
        return self.max_uses != 0 and self.uses >= self.max_uses

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= timezone.now()

    def is_usable(self) -> bool:
        return self.is_active and not self.is_exhausted and not self.is_expired

    def consume(self, user: User | None = None) -> bool:
        """
        Atomically claim one use. Returns False if the code was exhausted, so
        two concurrent signups cannot both take the last use of a code.
        """
        qs = AccessCode.objects.filter(pk=self.pk).usable()
        updated = qs.update(uses=models.F("uses") + 1)
        if not updated:
            return False
        if user is not None:
            AccessCodeRedemption.objects.create(access_code=self, user=user)
        self.refresh_from_db(fields=["uses"])
        return True


class AccessCodeRedemption(models.Model):
    """Audit trail of which account was created with which code."""

    access_code = models.ForeignKey(
        AccessCode, on_delete=models.CASCADE, related_name="redemptions"
    )
    user = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="access_code_redemptions"
    )
    redeemed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-redeemed_at",)

    def __str__(self) -> str:
        return f"{self.user} redeemed {self.access_code}"
