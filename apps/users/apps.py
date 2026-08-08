from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = "apps.users"
    label = "users"
    verbose_name = "Users"

    def ready(self):
        from apps.users import checks  # noqa: F401
