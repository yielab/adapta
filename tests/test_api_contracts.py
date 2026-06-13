"""
Contract tests — validate that the running app matches the OpenAPI spec.
Run with: make test-contracts (requires server on :8000)

These tests use schemathesis to auto-generate property-based test cases from
specs/openapi.yaml and assert the live server honours every declared response.
"""

import os

import pytest

schemathesis = pytest.importorskip(
    "schemathesis", reason="schemathesis not installed — run with [dev] extras"
)

pytestmark = pytest.mark.contract

SPEC_PATH = os.path.join(os.path.dirname(__file__), "..", "specs", "openapi.yaml")
BASE_URL = os.environ.get("BRAIN_BASE_URL", "http://localhost:8000/v1")
BEARER_TOKEN = os.environ.get("BRAIN_BEARER_TOKEN", "")

try:
    # schemathesis 4.x moved loaders to schemathesis.openapi.*
    schema = schemathesis.openapi.from_path(SPEC_PATH, base_url=BASE_URL)
except Exception as _e:
    pytest.skip(f"schemathesis schema loading failed: {_e}", allow_module_level=True)


@schema.auth()
class BrainBearerAuth:
    """Inject JWT Bearer token on every request that declares BearerAuth security."""

    def get(self, case, context):
        return BEARER_TOKEN

    def set(self, case, data, context):
        case.headers = case.headers or {}
        if data:
            case.headers["Authorization"] = f"Bearer {data}"


# ---------------------------------------------------------------------------
# Default contract sweep — exercises every declared (method, path) pair
# ---------------------------------------------------------------------------


@schema.parametrize()
def test_api_contract(case):
    """
    For every (method, path) pair in the spec, assert:
    - Response status code is one of the declared codes.
    - Response body matches the declared schema.
    - No 5xx for valid inputs.
    """
    response = case.call(timeout=30)
    case.validate_response(response)


# ---------------------------------------------------------------------------
# Focused high-value paths
# ---------------------------------------------------------------------------


@schema.parametrize(endpoint="/auth/login", method="POST")
def test_login_contract(case):
    response = case.call(timeout=15)
    case.validate_response(response)


@schema.parametrize(endpoint="/projects", method="GET")
def test_list_projects_contract(case):
    response = case.call(timeout=15)
    case.validate_response(response)


@schema.parametrize(endpoint="/chat/completions", method="POST")
def test_chat_completion_contract(case):
    response = case.call(timeout=60)
    case.validate_response(response)
