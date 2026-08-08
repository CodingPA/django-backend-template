"""
Celery tasks.

Autodiscovered by config/celery.py. With no broker configured,
CELERY_TASK_ALWAYS_EAGER makes .delay() run inline, so a fresh clone exercises
task code without Redis running.
"""

import logging

from celery import shared_task
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


@shared_task(name="core.ping")
def ping() -> str:
    """Trivial task for verifying a worker is connected."""
    return "pong"


@shared_task(
    name="core.send_email",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_email(self, subject: str, body: str, to: list[str], html: str | None = None):
    """
    Send mail off the request thread so a slow SMTP server cannot stall a
    signup response.
    """
    message = EmailMultiAlternatives(subject=subject, body=body, to=to)
    if html:
        message.attach_alternative(html, "text/html")
    message.send()
    logger.info("Sent %r to %s", subject, to)
