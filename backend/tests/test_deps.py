import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar, cast

from auth.auth_service import AuthService
from config.settings.schemas import AuthSettings, RedisSettings
from deps import redis_dep
from deps.auth_dep import get_auth_service, get_auth_settings, get_auth_task_queue
from deps.redis_dep import RedisClient, get_redis_client
from deps.settings_dep import get_required_settings
from deps.temporal_dep import get_temporal_client
from fastapi import FastAPI, Request
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client
from utils.otp_utils import OTPUtil

AsyncReturn = TypeVar("AsyncReturn")


class FakeLoader:
    def __init__(self):
        self.calls: list[tuple[dict[str, object], type[object]]] = []

    def get_required_settings(
        self,
        loaded_settings: dict[str, object],
        settings_schema: type[object],
    ) -> object:
        self.calls.append((loaded_settings, settings_schema))
        return settings_schema()


class FakeState:
    def __init__(self):
        self.settings_loader = FakeLoader()
        self.settings = {"settings": object()}
        self.redis_client = object()
        self.temporal_client = object()


def run_async(value: Coroutine[Any, Any, AsyncReturn]) -> AsyncReturn:
    return asyncio.run(value)


def make_request() -> Request:
    app = FastAPI()
    app.state.settings_loader = FakeLoader()
    app.state.settings = {"settings": object()}
    app.state.redis_client = object()
    app.state.temporal_client = object()
    return Request({"type": "http", "app": app})


def test_get_required_settings_reads_loader_from_app_state() -> None:
    request = make_request()

    settings = run_async(get_required_settings(request, RedisSettings))

    assert isinstance(settings, RedisSettings)
    assert request.app.state.settings_loader.calls == [
        (request.app.state.settings, RedisSettings)
    ]


def test_get_auth_settings_reads_loader_from_app_state() -> None:
    request = make_request()

    settings = run_async(get_auth_settings(request))

    assert isinstance(settings, AuthSettings)
    assert request.app.state.settings_loader.calls == [
        (request.app.state.settings, AuthSettings)
    ]


def test_get_auth_task_queue_reads_env(monkeypatch) -> None:
    monkeypatch.setenv("TEMPORAL_EMAIL_TASK_QUEUE", "auth-email-queue")

    assert get_auth_task_queue() == "auth-email-queue"


def test_get_auth_task_queue_uses_default(monkeypatch) -> None:
    monkeypatch.delenv("TEMPORAL_EMAIL_TASK_QUEUE", raising=False)

    assert get_auth_task_queue() == "manudocs-email"


async def resolve_auth_service(
    db_session: AsyncSession,
    otp_util: OTPUtil,
    auth_settings: AuthSettings,
    temporal_client: Client,
    task_queue: str,
) -> AuthService:
    async for service in get_auth_service(
        db_session,
        otp_util,
        auth_settings,
        temporal_client,
        task_queue,
    ):
        return service
    raise AssertionError("auth service dependency did not yield")


def test_get_auth_service_builds_service() -> None:
    db_session = cast(AsyncSession, object())
    otp_util = cast(OTPUtil, object())
    auth_settings = AuthSettings()
    temporal_client = cast(Client, object())

    service = run_async(
        resolve_auth_service(
            db_session,
            otp_util,
            auth_settings,
            temporal_client,
            "auth-email-queue",
        )
    )

    assert isinstance(service, AuthService)
    assert service._db_session is db_session
    assert service._otp_util is otp_util
    assert service._auth_settings is auth_settings
    assert service._temporal_client is temporal_client
    assert service._task_queue == "auth-email-queue"


def test_get_redis_client_reads_client_from_app_state() -> None:
    request = make_request()

    redis_client = run_async(get_redis_client(request))

    assert redis_client is request.app.state.redis_client


def test_get_temporal_client_reads_client_from_app_state() -> None:
    request = make_request()

    temporal_client = run_async(get_temporal_client(request))

    assert temporal_client is request.app.state.temporal_client


def test_redis_client_builds_client_from_settings(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    fake_client = object()

    def fake_from_url(url: str, *, max_connections: int) -> object:
        calls.append({"url": url, "max_connections": max_connections})
        return fake_client

    monkeypatch.setattr(redis_dep.Redis, "from_url", fake_from_url)

    client = RedisClient(
        RedisSettings(
            url=SecretStr("redis://localhost:6379/4"),
            max_connections=17,
        )
    )

    assert client.client is fake_client
    assert calls == [{"url": "redis://localhost:6379/4", "max_connections": 17}]
