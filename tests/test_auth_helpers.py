"""
Unit tests for the infra-free auth helpers (brain/services/auth.py):
password hashing (direct bcrypt + SHA-256 pre-hash), JWT round-trip, and scoped
API-key generation/verification. These are security-critical and pure, so they
belong in the offline gate. DB-touching helpers (create_user, authenticate_user)
are exercised by integration tests.
"""

import pytest

from brain.domain.errors import Unauthorized
from brain.services.auth import (
    create_access_token,
    decode_access_token,
    generate_api_key,
    hash_password,
    verify_api_key,
    verify_password,
)

# --- Password hashing (bcrypt + sha256 pre-hash) ---------------------------


def test_hash_password_is_salted_and_verifies():
    h1 = hash_password("correct horse battery staple")
    h2 = hash_password("correct horse battery staple")
    assert h1 != h2  # random per-hash salt
    assert verify_password("correct horse battery staple", h1)
    assert verify_password("correct horse battery staple", h2)


def test_verify_password_rejects_wrong_password():
    h = hash_password("s3cret-pass")
    assert verify_password("s3cret-pass", h)
    assert not verify_password("wrong-pass", h)


def test_verify_password_handles_malformed_hash():
    # Must not raise on a non-bcrypt string — returns False.
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_long_password_does_not_raise_72_byte_limit():
    # The SHA-256 pre-hash collapses any length to 44 bytes, sidestepping
    # bcrypt's hard 72-byte ceiling (the bug that broke registration).
    long_pw = "x" * 500
    h = hash_password(long_pw)
    assert verify_password(long_pw, h)
    # bytes 73..500 must not be ignored: a different long password fails.
    assert not verify_password("x" * 499 + "y", h)


# --- JWT round-trip --------------------------------------------------------


def test_jwt_roundtrip_carries_claims():
    token = create_access_token(user_id="u-1", org_id="org-9")
    payload = decode_access_token(token)
    assert payload["sub"] == "u-1"
    assert payload["org"] == "org-9"
    assert "exp" in payload


def test_decode_rejects_tampered_token():
    token = create_access_token(user_id="u-1", org_id="org-9")
    with pytest.raises(Unauthorized):
        decode_access_token(token + "tampered")


def test_decode_rejects_garbage():
    with pytest.raises(Unauthorized):
        decode_access_token("not.a.jwt")


# --- Scoped API keys -------------------------------------------------------


def test_generate_api_key_shape_and_verify():
    raw, prefix, stored_hash = generate_api_key()
    assert raw.startswith("brn_")
    assert prefix == raw[:8]
    assert stored_hash != raw  # only the hash is persisted
    assert verify_api_key(raw, stored_hash)


def test_api_key_verification_rejects_other_key():
    raw1, _, hash1 = generate_api_key()
    raw2, _, _ = generate_api_key()
    assert raw1 != raw2
    assert not verify_api_key(raw2, hash1)
