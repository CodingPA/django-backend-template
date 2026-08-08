"""Top-level WebSocket URL routing. Apps contribute their own patterns here."""

from apps.realtime.routing import websocket_urlpatterns as realtime_patterns

websocket_urlpatterns = [
    *realtime_patterns,
]
