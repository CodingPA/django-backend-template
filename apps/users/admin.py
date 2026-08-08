from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from apps.users import services
from apps.users.models import AccessCode, AccessCodeRedemption

User = get_user_model()


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "is_active", "is_staff", "date_joined")
    list_filter = ("is_active", "is_staff", "is_superuser", "date_joined")
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name")}),
        (
            _("Permissions"),
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)
    actions = ("action_sign_out_everywhere", "action_ban")

    @admin.action(description=_("Sign out of all devices"))
    def action_sign_out_everywhere(self, request, queryset):
        total = sum(services.invalidate_all_sessions(user) for user in queryset)
        self.message_user(request, f"Ended {total} session(s).", messages.SUCCESS)

    @admin.action(description=_("Deactivate and sign out everywhere"))
    def action_ban(self, request, queryset):
        for user in queryset:
            services.ban_user(user)
        self.message_user(request, f"Deactivated {queryset.count()} user(s).", messages.WARNING)


class RedemptionInline(admin.TabularInline):
    model = AccessCodeRedemption
    extra = 0
    readonly_fields = ("user", "redeemed_at")
    can_delete = False


@admin.register(AccessCode)
class AccessCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "uses", "max_uses", "expires_at", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "label")
    readonly_fields = ("uses", "created_at", "created_by")
    inlines = (RedemptionInline,)

    def get_changeform_initial_data(self, request):
        return {"code": AccessCode.generate_code()}

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.code = obj.code.strip().upper()
        super().save_model(request, obj, form, change)
