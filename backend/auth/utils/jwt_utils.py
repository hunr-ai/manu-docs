from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import uuid4

import jwt
from config.settings.schemas import AuthSettings
from db.models import User


class JWTTokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


def _timestamp(value: datetime) -> int:
    return int(value.timestamp())


def _user_claims(user: User) -> dict[str, str | int | None]:
    return {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "organization_id": user.organization_id,
    }


def create_token(
    user: User,
    settings: AuthSettings,
    token_type: JWTTokenType,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(UTC)
    if token_type is JWTTokenType.ACCESS:
        expires_at = issued_at + timedelta(minutes=settings.access_expiration_minutes)
        audience = settings.access_token_audience
        scope = settings.access_token_scope
    else:
        expires_at = issued_at + timedelta(minutes=settings.refresh_expiration_minutes)
        audience = settings.refresh_token_audience
        scope = settings.refresh_token_scope

    payload = {
        **_user_claims(user),
        "type": token_type.value,
        "scope": scope,
        "aud": audience,
        "iss": settings.jwt_issuer,
        "iat": _timestamp(issued_at),
        "exp": _timestamp(expires_at),
        "jti": str(uuid4()),
    }
    return jwt.encode(
        payload,
        settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def create_access_token(user: User, settings: AuthSettings) -> str:
    return create_token(user, settings, JWTTokenType.ACCESS)


def create_refresh_token(user: User, settings: AuthSettings) -> str:
    return create_token(user, settings, JWTTokenType.REFRESH)


def create_token_pair(user: User, settings: AuthSettings) -> tuple[str, str]:
    return create_access_token(user, settings), create_refresh_token(user, settings)


def decode_refresh_token(token: str, settings: AuthSettings) -> dict[str, object]:
    payload = jwt.decode(
        token,
        settings.secret_key.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
        audience=settings.refresh_token_audience,
        issuer=settings.jwt_issuer,
    )
    if payload.get("type") != JWTTokenType.REFRESH.value:
        raise jwt.InvalidTokenError("token is not a refresh token")
    if payload.get("scope") != settings.refresh_token_scope:
        raise jwt.InvalidTokenError("token scope is invalid")
    return payload
