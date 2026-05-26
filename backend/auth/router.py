from typing import Annotated

import jwt
from deps.auth_dep import get_auth_service
from fastapi import APIRouter, Depends, HTTPException, status
from utils.otp_utils import OTPErrorCode, OTPUtilError

from .auth_service import AuthService, AuthServiceError
from .dto.auth_request_dto import (
    PasswordlessLoginRequestDTO,
    PasswordlessLoginResponseDTO,
    PasswordlessVerifyRequestDTO,
    RefreshTokenRequestDTO,
    SignupRequestDTO,
    SignupVerifyRequestDTO,
    TokenPairResponseDTO,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _auth_error_to_http(exc: AuthServiceError) -> HTTPException:
    if exc.message == "user not found":
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        )
    if exc.message == "user already exists":
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="user already exists",
        )
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=exc.message,
    )


def _otp_error_to_http(exc: OTPUtilError) -> HTTPException:
    if exc.code is OTPErrorCode.COOLDOWN_NOT_ELAPSED:
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="otp cooldown has not elapsed",
        )
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="otp attempt limit reached",
    )


@router.post("/passwordless/request", response_model=PasswordlessLoginResponseDTO)
async def request_passwordless_login(
    request: PasswordlessLoginRequestDTO,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> PasswordlessLoginResponseDTO:
    try:
        return await auth_service.passwordless_login(request)
    except OTPUtilError as exc:
        raise _otp_error_to_http(exc) from exc
    except AuthServiceError as exc:
        raise _auth_error_to_http(exc) from exc


@router.post("/passwordless/resend", response_model=PasswordlessLoginResponseDTO)
async def resend_passwordless_login(
    request: PasswordlessLoginRequestDTO,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> PasswordlessLoginResponseDTO:
    try:
        return await auth_service.resend_passwordless_login(request)
    except OTPUtilError as exc:
        raise _otp_error_to_http(exc) from exc
    except AuthServiceError as exc:
        raise _auth_error_to_http(exc) from exc


@router.post("/signup/request", response_model=PasswordlessLoginResponseDTO)
async def request_signup(
    request: SignupRequestDTO,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> PasswordlessLoginResponseDTO:
    try:
        return await auth_service.signup(request)
    except OTPUtilError as exc:
        raise _otp_error_to_http(exc) from exc
    except AuthServiceError as exc:
        raise _auth_error_to_http(exc) from exc


@router.post("/signup/verify", response_model=TokenPairResponseDTO)
async def verify_signup(
    request: SignupVerifyRequestDTO,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenPairResponseDTO:
    try:
        return await auth_service.verify_signup(request)
    except AuthServiceError as exc:
        raise _auth_error_to_http(exc) from exc


@router.post("/passwordless/verify", response_model=TokenPairResponseDTO)
async def verify_passwordless_login(
    request: PasswordlessVerifyRequestDTO,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenPairResponseDTO:
    try:
        return await auth_service.verify_passwordless_login(request)
    except AuthServiceError as exc:
        raise _auth_error_to_http(exc) from exc


@router.post("/refresh", response_model=TokenPairResponseDTO)
async def refresh_tokens(
    request: RefreshTokenRequestDTO,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenPairResponseDTO:
    try:
        return await auth_service.refresh_tokens(request.refresh_token)
    except (jwt.InvalidTokenError, AuthServiceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid refresh token",
        ) from exc
