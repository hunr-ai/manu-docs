from collections.abc import AsyncIterator

import jwt
import pytest
from auth.auth_service import AuthServiceError
from auth.dto.auth_request_dto import (
    PasswordlessLoginResponseDTO,
    TokenPairResponseDTO,
)
from auth.router import router
from deps.auth_dep import get_auth_service
from fastapi import FastAPI
from fastapi.testclient import TestClient
from utils.otp_utils import OTPErrorCode, OTPUtilError


class FakeAuthService:
    def __init__(self):
        self.requests: list[object] = []
        self.error: Exception | None = None

    async def passwordless_login(self, request: object) -> PasswordlessLoginResponseDTO:
        self.requests.append(request)
        if self.error:
            raise self.error
        return PasswordlessLoginResponseDTO(success=True, message="queued")

    async def resend_passwordless_login(
        self, request: object
    ) -> PasswordlessLoginResponseDTO:
        self.requests.append(request)
        if self.error:
            raise self.error
        return PasswordlessLoginResponseDTO(success=True, message="queued")

    async def signup(self, request: object) -> PasswordlessLoginResponseDTO:
        self.requests.append(request)
        if self.error:
            raise self.error
        return PasswordlessLoginResponseDTO(success=True, message="signup queued")

    async def verify_signup(self, request: object) -> TokenPairResponseDTO:
        self.requests.append(request)
        if self.error:
            raise self.error
        return TokenPairResponseDTO(
            access_token="access",
            refresh_token="refresh",
            expires_in=60,
            refresh_expires_in=120,
        )

    async def verify_passwordless_login(self, request: object) -> TokenPairResponseDTO:
        self.requests.append(request)
        if self.error:
            raise self.error
        return TokenPairResponseDTO(
            access_token="access",
            refresh_token="refresh",
            expires_in=60,
            refresh_expires_in=120,
        )

    async def refresh_tokens(self, refresh_token: str) -> TokenPairResponseDTO:
        self.requests.append(refresh_token)
        if self.error:
            raise self.error
        return TokenPairResponseDTO(
            access_token="access",
            refresh_token="refresh",
            expires_in=60,
            refresh_expires_in=120,
        )


def make_client(service: FakeAuthService) -> TestClient:
    app = FastAPI()
    app.include_router(router)

    async def override_get_auth_service() -> AsyncIterator[FakeAuthService]:
        yield service

    app.dependency_overrides[get_auth_service] = override_get_auth_service
    return TestClient(app)


def test_request_passwordless_login_normalizes_payload_email() -> None:
    service = FakeAuthService()
    client = make_client(service)

    response = client.post(
        "/auth/passwordless/request",
        json={"email": " Person@Example.Test "},
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "queued"}
    assert service.requests[0].email == "person@example.test"


def test_request_passwordless_login_maps_unknown_user_to_404() -> None:
    service = FakeAuthService()
    service.error = AuthServiceError("user not found")
    client = make_client(service)

    response = client.post(
        "/auth/passwordless/request",
        json={"email": "missing@example.test"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "user not found"}


def test_resend_maps_otp_cooldown_to_429() -> None:
    service = FakeAuthService()
    service.error = OTPUtilError(OTPErrorCode.COOLDOWN_NOT_ELAPSED)
    client = make_client(service)

    response = client.post(
        "/auth/passwordless/resend",
        json={"email": "person@example.test"},
    )

    assert response.status_code == 429
    assert response.json() == {"detail": "otp cooldown has not elapsed"}


def test_signup_request_normalizes_payload_email() -> None:
    service = FakeAuthService()
    client = make_client(service)

    response = client.post(
        "/auth/signup/request",
        json={"email": " Person@Example.Test "},
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "signup queued"}
    assert service.requests[0].email == "person@example.test"


def test_signup_request_maps_duplicate_user_to_409() -> None:
    service = FakeAuthService()
    service.error = AuthServiceError("user already exists")
    client = make_client(service)

    response = client.post(
        "/auth/signup/request",
        json={"email": "person@example.test"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "user already exists"}


def test_signup_verify_returns_token_pair() -> None:
    service = FakeAuthService()
    client = make_client(service)

    response = client.post(
        "/auth/signup/verify",
        json={"email": "person@example.test", "otp": "123456"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "access",
        "refresh_token": "refresh",
        "token_type": "bearer",
        "expires_in": 60,
        "refresh_expires_in": 120,
    }
    assert service.requests[0].email == "person@example.test"


def test_verify_maps_invalid_otp_to_401() -> None:
    service = FakeAuthService()
    service.error = AuthServiceError("invalid otp")
    client = make_client(service)

    response = client.post(
        "/auth/passwordless/verify",
        json={"email": "person@example.test", "otp": "000000"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid otp"}


def test_refresh_returns_token_pair() -> None:
    service = FakeAuthService()
    client = make_client(service)

    response = client.post("/auth/refresh", json={"refresh_token": "token"})

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "access",
        "refresh_token": "refresh",
        "token_type": "bearer",
        "expires_in": 60,
        "refresh_expires_in": 120,
    }
    assert service.requests == ["token"]


@pytest.mark.parametrize("error", [jwt.InvalidTokenError(), AuthServiceError("bad")])
def test_refresh_maps_token_errors_to_401(error: Exception) -> None:
    service = FakeAuthService()
    service.error = error
    client = make_client(service)

    response = client.post("/auth/refresh", json={"refresh_token": "token"})

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid refresh token"}
