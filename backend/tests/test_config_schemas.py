import pytest
from config.settings.schemas.auth_settings import AuthSettings
from config.settings.schemas.base_settings import SettingsBase
from config.settings.schemas.db_settings import DatabaseSettings
from pydantic import SecretStr


def test_base_settings_requires_settings_name() -> None:
    with pytest.raises(NotImplementedError, match="Subclasses must implement"):
        SettingsBase().get_settings_name()


def test_append_field_name_formats_settings_key() -> None:
    settings = SettingsBase()

    assert (
        settings._get_append_field_name("access_expiration_minutes", "auth")
        == "auth-access-expiration-minutes"
    )


def test_auth_settings_defaults_and_name() -> None:
    settings = AuthSettings()

    assert settings.get_settings_name() == "auth"
    assert isinstance(settings.secret_key, SecretStr)
    assert settings.secret_key.get_secret_value() == "supersecretkey"
    assert settings.access_expiration_minutes == 60 * 24
    assert settings.refresh_expiration_minutes == 60 * 24 * 30


def test_auth_settings_config_and_secret_keys() -> None:
    settings = AuthSettings()

    assert settings.get_configs_secrets() == {
        "configs": [
            "auth-access-expiration-minutes",
            "auth-refresh-expiration-minutes",
        ],
        "secrets": ["auth-secret-key"],
    }


def test_database_settings_defaults_and_name() -> None:
    settings = DatabaseSettings()

    assert settings.get_settings_name() == "db"
    assert isinstance(settings.url, SecretStr)
    assert (
        settings.url.get_secret_value()
        == "postgresql+asyncpg://manudocsuser:manudocs@localhost:5432/manudocsdb"
    )
    assert settings.pool_size == 5
    assert settings.max_overflow == 10


def test_database_settings_config_and_secret_keys() -> None:
    settings = DatabaseSettings()

    assert settings.get_configs_secrets() == {
        "configs": ["db-pool-size", "db-max-overflow"],
        "secrets": ["db-url"],
    }
