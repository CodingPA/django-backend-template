from django.urls import path

from apps.core import api

app_name = "core"

urlpatterns = [
    path("config/", api.ConfigView.as_view(), name="config"),
    path("health/", api.HealthView.as_view(), name="health"),
]
