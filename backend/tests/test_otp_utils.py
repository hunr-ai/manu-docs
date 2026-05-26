import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar, cast

import pytest
from config.settings.schemas import OTPSettings
from utils.otp_utils import OTPErrorCode, OTPUtil, OTPUtilError, get_otp_settings

AsyncReturn = TypeVar("AsyncReturn")


class FakeRedisPipeline:
    def __init__(self, redis: "FakeRedis"):
        self._redis = redis

    def hset(self, key: str, mapping: dict[str, str | int]) -> None:
        self._redis.hashes[key] = dict(mapping)

    def expire(self, key: str, seconds: int) -> None:
        self._redis.expiry[key] = seconds

    def incr(self, key: str) -> None:
        value = int(self._redis.values.get(key, 0)) + 1
        self._redis.values[key] = value

    async def execute(self) -> list[object]:
        return []


class FakeRedis:
    def __init__(self):
        self.hashes: dict[str, dict[str, str | int]] = {}
        self.values: dict[str, str | int] = {}
        self.expiry: dict[str, int] = {}

    def pipeline(self) -> FakeRedisPipeline:
        return FakeRedisPipeline(self)

    async def hgetall(self, key: str) -> dict[str, str | int]:
        return self.hashes.get(key, {}).copy()

    async def get(self, key: str) -> str | int | None:
        return self.values.get(key)

    async def incr(self, key: str) -> int:
        value = int(self.values.get(key, 0)) + 1
        self.values[key] = value
        return value

    async def delete(self, key: str) -> int:
        deleted = int(key in self.hashes or key in self.values)
        self.hashes.pop(key, None)
        self.values.pop(key, None)
        return deleted


class FakeSettingsLoader:
    def get_required_settings(
        self,
        loaded_settings: dict[str, object],
        settings_schema: type[OTPSettings],
    ) -> OTPSettings:
        return cast(OTPSettings, loaded_settings[settings_schema.__name__])


class FakeAppState:
    def __init__(self, settings: dict[str, object]):
        self.settings_loader = FakeSettingsLoader()
        self.settings = settings


class FakeApp:
    def __init__(self, settings: dict[str, object]):
        self.state = FakeAppState(settings)


class FakeRequest:
    def __init__(self, settings: dict[str, object]):
        self.app = FakeApp(settings)


def run_async(value: Coroutine[Any, Any, AsyncReturn]) -> AsyncReturn:
    return asyncio.run(value)


def make_otp_util(
    redis: FakeRedis,
    *,
    cooldown_seconds: int = 300,
    expiry_seconds: int = 900,
    max_attempts_per_day: int = 5,
) -> OTPUtil:
    return OTPUtil(
        cast(Any, redis),
        OTPSettings(
            cooldown_seconds=cooldown_seconds,
            expiry_seconds=expiry_seconds,
            max_attempts_per_day=max_attempts_per_day,
        ),
    )


def test_generate_otp_stores_state_and_verify_deletes_it() -> None:
    redis = FakeRedis()
    otp_util = make_otp_util(redis)

    otp = run_async(otp_util.generate_otp("Person@Example.com"))

    assert len(otp) == 6
    assert "otp:person@example.com" in redis.hashes
    assert redis.hashes["otp:person@example.com"]["otp"] == otp
    assert redis.expiry["otp:person@example.com"] == 900
    assert run_async(otp_util.verify_otp("person@example.com", otp)) is True
    assert "otp:person@example.com" not in redis.hashes
    assert run_async(otp_util.verify_otp("person@example.com", otp)) is False


def test_generate_otp_raises_coded_error_when_cooldown_has_not_elapsed() -> None:
    redis = FakeRedis()
    otp_util = make_otp_util(redis, cooldown_seconds=300)

    run_async(otp_util.generate_otp("person@example.com"))

    with pytest.raises(OTPUtilError) as exc_info:
        run_async(otp_util.generate_otp("person@example.com"))

    assert exc_info.value.code is OTPErrorCode.COOLDOWN_NOT_ELAPSED
    assert str(exc_info.value) == "OTP cooldown has not elapsed"


def test_generate_otp_raises_coded_error_when_attempt_limit_is_reached() -> None:
    redis = FakeRedis()
    otp_util = make_otp_util(redis, max_attempts_per_day=1)

    otp = run_async(otp_util.generate_otp("person@example.com"))
    assert run_async(otp_util.verify_otp("person@example.com", otp)) is True

    with pytest.raises(OTPUtilError) as exc_info:
        run_async(otp_util.generate_otp("person@example.com"))

    assert exc_info.value.code is OTPErrorCode.ATTEMPT_LIMIT_REACHED
    assert str(exc_info.value) == "OTP attempt limit reached"


def test_verify_otp_rejects_incorrect_code_without_deleting_state() -> None:
    redis = FakeRedis()
    otp_util = make_otp_util(redis)

    otp = run_async(otp_util.generate_otp("person@example.com"))

    assert run_async(otp_util.verify_otp("person@example.com", "000000")) is False
    assert "otp:person@example.com" in redis.hashes
    assert run_async(otp_util.verify_otp("person@example.com", otp)) is True


def test_get_otp_settings_returns_typed_settings_from_request_state() -> None:
    otp_settings = OTPSettings(cooldown_seconds=30)
    request = FakeRequest({"OTPSettings": otp_settings})

    assert run_async(get_otp_settings(cast(Any, request))) is otp_settings
