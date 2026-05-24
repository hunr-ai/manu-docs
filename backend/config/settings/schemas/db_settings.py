from pydantic import Field, SecretStr

from .base_settings import SettingsBase


class DatabaseSettings(SettingsBase):
    url: SecretStr = Field(
        default=SecretStr(
            "postgresql+asyncpg://manudocsuser:manudocs@localhost:5432/manudocsdb"
        )
    )
    pool_size: int = Field(default=5)
    max_overflow: int = Field(default=10)

    def get_settings_name(self) -> str:
        return "db"
