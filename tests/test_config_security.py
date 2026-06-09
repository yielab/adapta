"""Tests for the production security fail-fast in brain.config.Settings (§4.3).

The validator must reject weak defaults ONLY in production, leaving development
and CI (which default BRAIN_ENVIRONMENT to development) untouched.
"""

from __future__ import annotations

import pytest

from brain.config import _DEFAULT_SECRET, Settings

STRONG = "x" * 40
GOOD_DB = "postgresql+asyncpg://brain:s3cr3t-pass@postgres:5432/brain"
DEFAULT_DB = "postgresql+asyncpg://brain:brain@postgres:5432/brain"


def _settings(**over):
    base = dict(
        environment="production",
        secret_key=STRONG,
        database_url=GOOD_DB,
        cors_origins=["https://app.example.com"],
    )
    base.update(over)
    return Settings(**base)


def test_development_allows_weak_defaults():
    # The default environment is development → validator is a no-op.
    s = Settings(secret_key=_DEFAULT_SECRET, database_url=DEFAULT_DB, cors_origins=["*"])
    assert s.environment == "development"


def test_production_rejects_default_secret():
    with pytest.raises(ValueError, match="BRAIN_SECRET_KEY"):
        _settings(secret_key=_DEFAULT_SECRET)


def test_production_rejects_short_secret():
    with pytest.raises(ValueError, match="too short"):
        _settings(secret_key="short")


def test_production_rejects_default_db_password():
    with pytest.raises(ValueError, match="brain:brain"):
        _settings(database_url=DEFAULT_DB)


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValueError, match="CORS"):
        _settings(cors_origins=["*"])


def test_production_accepts_strong_config():
    s = _settings()
    assert s.environment == "production"
    assert s.secret_key == STRONG
