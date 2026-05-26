from pydantic import Field, SecretStr

from .base_settings import SettingsBase


class RedisSettings(SettingsBase):
    url: SecretStr = Field(default=SecretStr("redis://localhost:6379/0"))
    max_connections: int = Field(default=10)

    def get_settings_name(self) -> str:
        return "redis"
