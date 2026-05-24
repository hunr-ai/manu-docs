from pydantic import Field, SecretStr

from .base_settings import SettingsBase


class AuthSettings(SettingsBase):
    secret_key: SecretStr = Field(default=SecretStr("supersecretkey"))
    access_expiration_minutes: int = Field(default=60 * 24)  # 1 day
    refresh_expiration_minutes: int = Field(default=60 * 24 * 30)  # 30 days

    def get_settings_name(self) -> str:
        return "auth"
