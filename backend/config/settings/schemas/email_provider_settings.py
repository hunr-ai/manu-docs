from typing import Literal

from pydantic import SecretStr

from .base_settings import SettingsBase


class EmailProviderSettings(SettingsBase):
    provider: Literal["resend", "smtp", "console"] = "console"
    resend_api_key: SecretStr | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_use_tls: bool = True

    def get_settings_name(self) -> str:
        return "emailproviders"
