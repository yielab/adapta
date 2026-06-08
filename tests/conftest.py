"""
Pytest configuration.
Real integration tests require the full Docker stack (postgres, redis, chroma).
Unit tests mock infrastructure at the boundary.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from brain.api.app import app


@pytest.fixture
async def client():
    """Async test client for the FastAPI app."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
