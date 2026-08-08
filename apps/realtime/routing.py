from django.urls import path

from apps.realtime import consumers

websocket_urlpatterns = [
    path("ws/echo/", consumers.EchoConsumer.as_asgi()),
]
