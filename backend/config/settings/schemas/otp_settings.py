from pydantic import Field

from .base_settings import SettingsBase


class OTPSettings(SettingsBase):
    cooldown_seconds: int = Field(default=300, ge=1)
    expiry_seconds: int = Field(default=900, ge=1)
    max_attempts_per_day: int = Field(default=5, ge=1)

    def get_settings_name(self) -> str:
        return "otp"
