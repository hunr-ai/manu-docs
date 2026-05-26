from pydantic import Field, SecretStr

from .base_settings import SettingsBase


class AuthSettings(SettingsBase):
    secret_key: SecretStr = Field(default=SecretStr("supersecretkey"))
    jwt_algorithm: str = Field(default="HS256")
    jwt_issuer: str = Field(default="manudocs")
    access_token_audience: str = Field(default="manudocs-api")
    refresh_token_audience: str = Field(default="manudocs-auth")
    access_token_scope: str = Field(default="auth:access")
    refresh_token_scope: str = Field(default="auth:refresh")
    access_expiration_minutes: int = Field(default=60 * 24)  # 1 day
    refresh_expiration_minutes: int = Field(default=60 * 24 * 30)  # 30 days

    def get_settings_name(self) -> str:
        return "auth"
