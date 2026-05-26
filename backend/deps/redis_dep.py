from config.settings.schemas import RedisSettings
from fastapi import Request
from redis.asyncio import Redis

RedisConnection = Redis


class RedisClient:
    def __init__(self, settings: RedisSettings):
        self._settings = settings
        self.client = Redis.from_url(
            self._settings.url.get_secret_value(),
            max_connections=self._settings.max_connections,
        )


async def get_redis_client(request: Request) -> RedisConnection:
    return request.app.state.redis_client
