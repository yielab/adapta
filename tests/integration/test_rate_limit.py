"""
Integration test — §A4.9 auth brute-force rate limiting.

Hammering /v1/auth/login past the configured cap must return a typed 429 (the
documented `rate_limited` envelope), not let an attacker keep guessing. The
`client` fixture flushes the rate-limit counters first, so this starts from a
fresh window.
"""

import pytest

from brain.config import settings

pytestmark = pytest.mark.integration


async def test_login_is_rate_limited(client):
    if settings.auth_rate_limit_max <= 0:
        pytest.skip("auth rate limiting disabled (BRAIN_AUTH_RATE_LIMIT_MAX<=0)")
    seen_429 = False
    # A few over the cap guarantees we cross it even counting this IP's prior hits=0.
    for _ in range(settings.auth_rate_limit_max + 5):
        r = await client.post(
            "/v1/auth/login",
            json={"email": "nobody@itest.dev", "password": "wrong-pass"},
        )
        if r.status_code == 429:
            seen_429 = True
            assert r.json()["error"]["code"] == "rate_limited"
            break
        # Until the limit trips, a bad login is 401 (not 429).
        assert r.status_code == 401, r.text

    assert seen_429, f"never hit 429 within {settings.auth_rate_limit_max + 5} attempts"
