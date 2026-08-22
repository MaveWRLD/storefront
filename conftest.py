import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    # DRF's ScopedRateThrottle counters live in the default cache
    # (LocMemCache, process-wide for the whole test run) keyed by client
    # IP — every APIClient in the suite shares that IP, so counts from an
    # earlier test (or an earlier request in the same test) would
    # otherwise bleed into unrelated tests hitting the same throttled
    # endpoint (auth/jwt/create/, auth/users/, orders/lookup/).
    cache.clear()
    yield
    cache.clear()
