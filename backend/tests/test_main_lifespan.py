import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

import main
from config.settings.schemas import DatabaseSettings, RedisSettings
from fastapi import FastAPI
from pydantic import SecretStr

AsyncReturn = TypeVar("AsyncReturn")


class FakeSettingsLoader:
    def __init__(self):
        self.loaded_settings = {"settings": object()}

    async def load_settings(self) -> dict[str, object]:
        return self.loaded_settings

    def get_required_settings(
        self,
        loaded_settings: dict[str, object],
        settings_schema: type[DatabaseSettings] | type[RedisSettings],
    ) -> DatabaseSettings | RedisSettings:
        assert loaded_settings is self.loaded_settings
        if settings_schema is DatabaseSettings:
            return DatabaseSettings(
                url=SecretStr(
                    "postgresql+asyncpg://user:password@localhost:5432/appdb"
                ),
                pool_size=3,
                max_overflow=4,
            )
        if settings_schema is RedisSettings:
            return RedisSettings(
                url=SecretStr("redis://localhost:6379/2"),
                max_connections=11,
            )
        raise AssertionError("unexpected settings schema")


class FakeEngine:
    def __init__(self):
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


class FakeRedis:
    def __init__(self):
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class FakeRedisClient:
    last_settings: RedisSettings | None = None
    last_client: FakeRedis | None = None

    def __init__(self, settings: RedisSettings):
        self.__class__.last_settings = settings
        self.client = FakeRedis()
        self.__class__.last_client = self.client


class FakeTemporalClient:
    calls: list[dict[str, object]] = []

    @classmethod
    async def connect(cls, address: str, *, namespace: str) -> "FakeTemporalClient":
        cls.calls.append({"address": address, "namespace": namespace})
        return cls()


def run_async(value: Coroutine[Any, Any, AsyncReturn]) -> AsyncReturn:
    return asyncio.run(value)


def test_lifespan_wires_app_state_and_closes_clients(monkeypatch) -> None:
    settings_loader = FakeSettingsLoader()
    fake_engine = FakeEngine()
    sessionmaker = object()
    engine_calls: list[dict[str, object]] = []
    sessionmaker_calls: list[dict[str, object]] = []

    def fake_create_async_engine(url: str, **kwargs: object) -> FakeEngine:
        engine_calls.append({"url": url, **kwargs})
        return fake_engine

    def fake_async_sessionmaker(engine: object, **kwargs: object) -> object:
        sessionmaker_calls.append({"engine": engine, **kwargs})
        return sessionmaker

    monkeypatch.setattr(
        main, "get_settings_loader", lambda environment: settings_loader
    )
    monkeypatch.setattr(main, "create_async_engine", fake_create_async_engine)
    monkeypatch.setattr(main, "async_sessionmaker", fake_async_sessionmaker)
    monkeypatch.setattr(main, "RedisClient", FakeRedisClient)
    monkeypatch.setattr(main, "Client", FakeTemporalClient)

    app = FastAPI()

    async def run_lifespan() -> None:
        async with main.lifespan(app):
            assert app.state.settings_loader is settings_loader
            assert app.state.settings is settings_loader.loaded_settings
            assert app.state.db_engine is fake_engine
            assert app.state.db_sessionmaker is sessionmaker
            assert app.state.redis_client is FakeRedisClient.last_client
            assert isinstance(app.state.temporal_client, FakeTemporalClient)
            assert fake_engine.disposed is False
            assert FakeRedisClient.last_client is not None
            assert FakeRedisClient.last_client.closed is False

    run_async(run_lifespan())

    assert engine_calls == [
        {
            "url": "postgresql+asyncpg://user:password@localhost:5432/appdb",
            "pool_size": 3,
            "max_overflow": 4,
            "pool_pre_ping": True,
        }
    ]
    assert sessionmaker_calls == [
        {
            "engine": fake_engine,
            "expire_on_commit": False,
            "autoflush": False,
        }
    ]
    assert FakeRedisClient.last_settings is not None
    assert (
        FakeRedisClient.last_settings.url.get_secret_value()
        == "redis://localhost:6379/2"
    )
    assert FakeRedisClient.last_settings.max_connections == 11
    assert fake_engine.disposed is True
    assert FakeRedisClient.last_client is not None
    assert FakeRedisClient.last_client.closed is True
    assert FakeTemporalClient.calls == [
        {"address": "localhost:7233", "namespace": "default"}
    ]


def test_app_includes_email_tracking_routes() -> None:
    route_paths = {route.path for route in main.app.routes}

    assert "/emails/tracking/{tracking_token}.png" in route_paths
    assert "/emails/tracking/webhook" in route_paths
    assert "/auth/passwordless/request" in route_paths
    assert "/auth/passwordless/verify" in route_paths
    assert "/auth/passwordless/resend" in route_paths
    assert "/auth/refresh" in route_paths
