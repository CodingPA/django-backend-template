"""
Root pytest configuration.

The cache is not rolled back between tests the way the database is, and allauth
keeps both its rate limits and its email-confirmation cooldown there. Without
clearing it, a test that signs up the same address as an earlier one silently
gets no email, and a test that logs in repeatedly eventually gets throttled --
both of which look like flaky product bugs rather than shared state.
"""

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()
