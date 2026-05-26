import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar, cast

import jwt
import pytest
from auth.auth_service import AuthService, AuthServiceError
from auth.dto.auth_request_dto import (
    PasswordlessLoginRequestDTO,
    PasswordlessVerifyRequestDTO,
    SignupRequestDTO,
    SignupVerifyRequestDTO,
)
from auth.utils.jwt_utils import create_refresh_token
from config.settings.schemas import AuthSettings
from db.models import EmailTemplate, User, UserRole
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

AsyncReturn = TypeVar("AsyncReturn")


class FakeResult:
    def __init__(self, value: object | None):
        self._value = value

    def scalar_one_or_none(self) -> object | None:
        return self._value

    def scalar_one(self) -> object:
        if self._value is None:
            raise AssertionError("no scalar value")
        return self._value


class FakeSession:
    def __init__(self, user: User | None):
        self.user = user
        self.template = EmailTemplate(
            name="Login",
            use_case="login",
            subject="Code {{ otp }}",
            html_template="<strong>{{ otp }}</strong>",
            text_template="Code {{ otp }}",
        )
        self.statements: list[object] = []
        self.added: list[object] = []
        self.flushed = False
        self.committed = False

    async def execute(self, statement: object) -> FakeResult:
        self.statements.append(statement)
        if len(self.statements) == 1:
            return FakeResult(self.user)
        return FakeResult(self.template)

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flushed = True
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = 17

    async def commit(self) -> None:
        self.committed = True


class FakeOTPUtil:
    def __init__(self, verify_result: bool = True):
        self.verify_result = verify_result
        self.sent_to: list[str] = []
        self.verified: list[tuple[str, str]] = []

    async def generate_otp(self, email: str) -> str:
        self.sent_to.append(email)
        return "123456"

    async def verify_otp(self, email: str, otp: str) -> bool:
        self.verified.append((email, otp))
        return self.verify_result


class FakeTemporalClient:
    def __init__(self):
        self.started: list[dict[str, object]] = []

    async def start_workflow(self, workflow: object, request: object, **kwargs: object):
        self.started.append({"workflow": workflow, "request": request, **kwargs})
        return object()


def run_async(value: Coroutine[Any, Any, AsyncReturn]) -> AsyncReturn:
    return asyncio.run(value)


def make_user() -> User:
    user = User(
        email="person@example.test",
        organization_id=11,
        role=UserRole.MEMBER,
    )
    user.id = 5
    return user


def make_settings() -> AuthSettings:
    return AuthSettings(
        secret_key=SecretStr("auth-secret-with-at-least-thirty-two-bytes")
    )


def make_service(
    user: User | None,
    otp_util: FakeOTPUtil | None = None,
    temporal_client: FakeTemporalClient | None = None,
) -> tuple[AuthService, FakeOTPUtil, FakeTemporalClient]:
    otp_util = otp_util or FakeOTPUtil()
    temporal_client = temporal_client or FakeTemporalClient()
    service = AuthService(
        db_session=cast(AsyncSession, FakeSession(user)),
        otp_util=cast(Any, otp_util),
        auth_settings=make_settings(),
        temporal_client=cast(Any, temporal_client),
        task_queue="email-task-queue",
    )
    return service, otp_util, temporal_client


def test_passwordless_login_queues_temporal_email_with_debug_otp() -> None:
    service, otp_util, temporal_client = make_service(make_user())

    response = run_async(
        service.passwordless_login(
            PasswordlessLoginRequestDTO(email="Person@Example.Test")
        )
    )

    assert response.success is True
    assert otp_util.sent_to == ["person@example.test"]
    assert len(temporal_client.started) == 1
    started = temporal_client.started[0]
    request = cast(Any, started["request"])
    assert started["task_queue"] == "email-task-queue"
    assert started["id"] == request.tracking_token
    assert request.to == "person@example.test"
    assert request.subject == "Code 123456"
    assert request.debug_code == "123456"


def test_passwordless_login_rejects_unknown_user_without_sending_otp() -> None:
    service, otp_util, temporal_client = make_service(None)

    with pytest.raises(AuthServiceError, match="user not found"):
        run_async(
            service.passwordless_login(
                PasswordlessLoginRequestDTO(email="missing@example.test")
            )
        )

    assert otp_util.sent_to == []
    assert temporal_client.started == []


def test_signup_queues_temporal_email_for_new_user() -> None:
    service, otp_util, temporal_client = make_service(None)

    response = run_async(
        service.signup(SignupRequestDTO(email=" Person@Example.Test "))
    )

    assert response.success is True
    assert response.message == "signup email queued"
    assert otp_util.sent_to == ["person@example.test"]
    assert len(temporal_client.started) == 1
    request = cast(Any, temporal_client.started[0]["request"])
    assert request.to == "person@example.test"
    assert request.debug_code == "123456"


def test_signup_rejects_existing_user_without_sending_otp() -> None:
    service, otp_util, temporal_client = make_service(make_user())

    with pytest.raises(AuthServiceError, match="user already exists"):
        run_async(service.signup(SignupRequestDTO(email="person@example.test")))

    assert otp_util.sent_to == []
    assert temporal_client.started == []


def test_verify_signup_creates_owner_without_organization_and_returns_tokens() -> None:
    service, otp_util, _temporal_client = make_service(None)
    session = cast(Any, service)._db_session

    response = run_async(
        service.verify_signup(
            SignupVerifyRequestDTO(email="person@example.test", otp="123456")
        )
    )

    assert response.access_token
    assert response.refresh_token
    assert otp_util.verified == [("person@example.test", "123456")]
    assert session.flushed is True
    assert session.committed is True
    assert len(session.added) == 1
    user = cast(User, session.added[0])
    assert user.email == "person@example.test"
    assert user.organization_id is None
    assert user.role is UserRole.OWNER
    payload = jwt.decode(response.access_token, options={"verify_signature": False})
    assert payload["organization_id"] is None
    assert payload["role"] == "owner"


def test_verify_signup_rejects_invalid_otp_without_creating_user() -> None:
    service, _otp_util, _temporal_client = make_service(
        None, otp_util=FakeOTPUtil(verify_result=False)
    )
    session = cast(Any, service)._db_session

    with pytest.raises(AuthServiceError, match="invalid otp"):
        run_async(
            service.verify_signup(
                SignupVerifyRequestDTO(email="person@example.test", otp="000000")
            )
        )

    assert session.added == []
    assert session.committed is False


def test_verify_signup_rejects_existing_user_without_checking_otp() -> None:
    service, otp_util, _temporal_client = make_service(make_user())

    with pytest.raises(AuthServiceError, match="user already exists"):
        run_async(
            service.verify_signup(
                SignupVerifyRequestDTO(email="person@example.test", otp="123456")
            )
        )

    assert otp_util.verified == []


def test_verify_passwordless_login_returns_token_pair() -> None:
    service, otp_util, _temporal_client = make_service(make_user())

    response = run_async(
        service.verify_passwordless_login(
            PasswordlessVerifyRequestDTO(
                email="person@example.test",
                otp="123456",
            )
        )
    )

    assert response.token_type == "bearer"
    assert response.access_token
    assert response.refresh_token
    assert response.expires_in == 60 * 60 * 24
    assert response.refresh_expires_in == 60 * 60 * 24 * 30
    assert otp_util.verified == [("person@example.test", "123456")]


def test_verify_passwordless_login_rejects_invalid_otp() -> None:
    service, _otp_util, _temporal_client = make_service(
        make_user(), otp_util=FakeOTPUtil(verify_result=False)
    )

    with pytest.raises(AuthServiceError, match="invalid otp"):
        run_async(
            service.verify_passwordless_login(
                PasswordlessVerifyRequestDTO(
                    email="person@example.test",
                    otp="000000",
                )
            )
        )


def test_refresh_tokens_validates_refresh_token_and_reloads_user() -> None:
    user = make_user()
    token = create_refresh_token(user, make_settings())
    service, _otp_util, _temporal_client = make_service(user)

    response = run_async(service.refresh_tokens(token))

    assert response.access_token
    assert response.refresh_token
    assert response.refresh_token != token
