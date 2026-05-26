from datetime import UTC, datetime

import jwt
import pytest
from auth.utils.jwt_utils import (
    JWTTokenType,
    create_access_token,
    create_refresh_token,
    create_token,
    decode_refresh_token,
)
from config.settings.schemas import AuthSettings
from db.models import User, UserRole
from pydantic import SecretStr


def make_user() -> User:
    user = User(
        email="person@example.test",
        organization_id=42,
        role=UserRole.ADMIN,
    )
    user.id = 7
    return user


def make_settings() -> AuthSettings:
    return AuthSettings(
        secret_key=SecretStr("jwt-secret-with-at-least-thirty-two-bytes"),
        jwt_issuer="issuer.test",
        access_token_audience="api.test",
        refresh_token_audience="auth.test",
        access_expiration_minutes=15,
        refresh_expiration_minutes=30,
    )


def test_create_access_token_includes_identity_scope_and_audience() -> None:
    token = create_token(
        make_user(),
        make_settings(),
        JWTTokenType.ACCESS,
        now=datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
    )

    payload = jwt.decode(
        token,
        "jwt-secret-with-at-least-thirty-two-bytes",
        algorithms=["HS256"],
        audience="api.test",
        issuer="issuer.test",
        options={"verify_exp": False, "verify_iat": False},
    )

    assert payload["sub"] == "7"
    assert payload["email"] == "person@example.test"
    assert payload["role"] == "admin"
    assert payload["organization_id"] == 42
    assert payload["type"] == "access"
    assert payload["scope"] == "auth:access"
    assert payload["iat"] == 1779624000
    assert payload["exp"] == 1779624900
    assert payload["jti"]


def test_create_access_token_allows_missing_organization() -> None:
    user = make_user()
    user.organization_id = None

    token = create_access_token(user, make_settings())
    payload = jwt.decode(
        token,
        "jwt-secret-with-at-least-thirty-two-bytes",
        algorithms=["HS256"],
        audience="api.test",
        issuer="issuer.test",
    )

    assert payload["organization_id"] is None


def test_decode_refresh_token_accepts_only_refresh_tokens() -> None:
    settings = make_settings()
    refresh_token = create_refresh_token(make_user(), settings)

    payload = decode_refresh_token(refresh_token, settings)

    assert payload["type"] == "refresh"
    assert payload["scope"] == "auth:refresh"
    assert payload["aud"] == "auth.test"


def test_decode_refresh_token_rejects_access_token() -> None:
    settings = make_settings()
    access_token = create_access_token(make_user(), settings)

    with pytest.raises(jwt.InvalidTokenError):
        decode_refresh_token(access_token, settings)
