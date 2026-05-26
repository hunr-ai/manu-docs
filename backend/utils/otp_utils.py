import base64
import hashlib
import time
from dataclasses import dataclass
from enum import StrEnum
from inspect import isawaitable
from typing import Awaitable, TypeVar, cast

import pyotp
from config.settings.schemas import OTPSettings
from deps.redis_dep import RedisConnection, get_redis_client
from deps.settings_dep import get_required_settings
from fastapi import Depends, Request

RedisValue = str | bytes | int | None
RedisHash = dict[str | bytes, RedisValue]
RedisReturn = TypeVar("RedisReturn")


class OTPErrorCode(StrEnum):
    COOLDOWN_NOT_ELAPSED = "cooldown_not_elapsed"
    ATTEMPT_LIMIT_REACHED = "attempt_limit_reached"


OTP_ERROR_MESSAGES = {
    OTPErrorCode.COOLDOWN_NOT_ELAPSED: "OTP cooldown has not elapsed",
    OTPErrorCode.ATTEMPT_LIMIT_REACHED: "OTP attempt limit reached",
}


class OTPUtilError(Exception):
    def __init__(self, code: OTPErrorCode):
        self.code = code
        super().__init__(OTP_ERROR_MESSAGES[code])


@dataclass(frozen=True)
class OTPState:
    otp: str
    counter: int
    sent_at: int


class OTPUtil:
    def __init__(self, redis_client: RedisConnection, otp_settings: OTPSettings):
        self._redis = redis_client
        self._otp_settings = otp_settings

    def _email_key(self, email: str) -> str:
        return email.strip().lower()

    def _secret_for_email(self, email: str) -> str:
        digest = hashlib.sha256(self._email_key(email).encode("utf-8")).digest()
        return base64.b32encode(digest).decode("utf-8").rstrip("=")

    def _otp_key(self, email: str) -> str:
        return f"otp:{self._email_key(email)}"

    def _attempts_key(self, email: str) -> str:
        return f"otp-attempts:{self._email_key(email)}"

    def _counter_key(self, email: str) -> str:
        return f"otp-counter:{self._email_key(email)}"

    def _generate_otp(self, email: str, counter: int) -> str:
        return pyotp.HOTP(self._secret_for_email(email)).at(counter)

    async def _redis_result(
        self,
        value: RedisReturn | Awaitable[RedisReturn],
    ) -> RedisReturn:
        if isawaitable(value):
            return await cast(Awaitable[RedisReturn], value)

        return cast(RedisReturn, value)

    def _str_value(self, value: RedisValue) -> str | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    def _int_value(self, value: RedisValue) -> int | None:
        text = self._str_value(value)
        return None if text is None else int(text)

    async def _get_state(self, email: str) -> OTPState | None:
        state = cast(
            RedisHash,
            await self._redis_result(self._redis.hgetall(self._otp_key(email))),
        )
        if not state:
            return None

        otp = self._str_value(state.get("otp") or state.get(b"otp"))
        counter = self._int_value(state.get("counter") or state.get(b"counter"))
        sent_at = self._int_value(state.get("sent_at") or state.get(b"sent_at"))
        if otp is None or counter is None or sent_at is None:
            return None

        return OTPState(otp=otp, counter=counter, sent_at=sent_at)

    async def _save_state(self, email: str, state: OTPState) -> None:
        pipe = self._redis.pipeline()
        pipe.hset(
            self._otp_key(email),
            mapping={
                "otp": state.otp,
                "counter": state.counter,
                "sent_at": state.sent_at,
            },
        )
        pipe.expire(self._otp_key(email), self._otp_settings.expiry_seconds)
        await pipe.execute()

    async def _delete_state(self, email: str) -> None:
        await self._redis.delete(self._otp_key(email))

    async def _get_attempts(self, email: str) -> int:
        attempts = cast(
            RedisValue,
            await self._redis_result(self._redis.get(self._attempts_key(email))),
        )
        return self._int_value(attempts) or 0

    async def _increment_attempts(self, email: str) -> None:
        pipe = self._redis.pipeline()
        pipe.incr(self._attempts_key(email))
        pipe.expire(self._attempts_key(email), 60 * 60 * 24)
        await pipe.execute()

    async def _next_counter(self, email: str) -> int:
        counter = cast(
            RedisValue,
            await self._redis_result(self._redis.incr(self._counter_key(email))),
        )
        return self._int_value(counter) or 0

    async def generate_otp(self, email: str) -> str:
        now = int(time.time())
        state = await self._get_state(email)

        if (
            state is not None
            and now - state.sent_at < self._otp_settings.cooldown_seconds
        ):
            raise OTPUtilError(OTPErrorCode.COOLDOWN_NOT_ELAPSED)

        attempts = await self._get_attempts(email)
        if attempts >= self._otp_settings.max_attempts_per_day:
            raise OTPUtilError(OTPErrorCode.ATTEMPT_LIMIT_REACHED)

        counter = await self._next_counter(email)
        otp = self._generate_otp(email, counter)
        await self._save_state(email, OTPState(otp=otp, counter=counter, sent_at=now))
        await self._increment_attempts(email)
        return otp

    async def verify_otp(self, email: str, otp: str) -> bool:
        state = await self._get_state(email)
        if state is None or state.otp != otp:
            return False

        await self._delete_state(email)
        return True


async def get_otp_settings(request: Request) -> OTPSettings:
    settings = await get_required_settings(request, OTPSettings)
    return cast(OTPSettings, settings)


async def get_otp_util(
    redis_client: RedisConnection = Depends(get_redis_client),
    otp_settings: OTPSettings = Depends(get_otp_settings),
) -> OTPUtil:
    return OTPUtil(redis_client, otp_settings)
