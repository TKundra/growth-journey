"""Unit tests for password hashing + JWT helpers (no database needed)."""

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_roundtrip():
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert verify_password("secret123", hashed)


def test_wrong_password_fails():
    hashed = hash_password("secret123")
    assert not verify_password("not-it", hashed)


def test_long_password_truncated_consistently():
    # >72 bytes must not raise and must verify against the same input.
    long_pw = "a" * 200
    hashed = hash_password(long_pw)
    assert verify_password(long_pw, hashed)


def test_token_roundtrip():
    token = create_access_token("some-public-id")
    assert decode_access_token(token) == "some-public-id"


def test_bad_token_returns_none():
    assert decode_access_token("not.a.jwt") is None
