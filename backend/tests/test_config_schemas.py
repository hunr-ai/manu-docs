import pytest
from config.settings.schemas.auth_settings import AuthSettings
from config.settings.schemas.base_settings import SettingsBase
from config.settings.schemas.db_settings import DatabaseSettings
from config.settings.schemas.email_provider_settings import EmailProviderSettings
from config.settings.schemas.otp_settings import OTPSettings
from config.settings.schemas.redis_settings import RedisSettings
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
    assert settings.jwt_algorithm == "HS256"
    assert settings.jwt_issuer == "manudocs"
    assert settings.access_token_audience == "manudocs-api"
    assert settings.refresh_token_audience == "manudocs-auth"
    assert settings.access_token_scope == "auth:access"
    assert settings.refresh_token_scope == "auth:refresh"
    assert settings.access_expiration_minutes == 60 * 24
    assert settings.refresh_expiration_minutes == 60 * 24 * 30


def test_auth_settings_config_and_secret_keys() -> None:
    settings = AuthSettings()

    assert settings.get_configs_secrets() == {
        "configs": [
            "auth-jwt-algorithm",
            "auth-jwt-issuer",
            "auth-access-token-audience",
            "auth-refresh-token-audience",
            "auth-access-token-scope",
            "auth-refresh-token-scope",
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


def test_redis_settings_defaults_and_name() -> None:
    settings = RedisSettings()

    assert settings.get_settings_name() == "redis"
    assert isinstance(settings.url, SecretStr)
    assert settings.url.get_secret_value() == "redis://localhost:6379/0"
    assert settings.max_connections == 10


def test_redis_settings_config_and_secret_keys() -> None:
    settings = RedisSettings()

    assert settings.get_configs_secrets() == {
        "configs": ["redis-max-connections"],
        "secrets": ["redis-url"],
    }


def test_otp_settings_defaults_and_name() -> None:
    settings = OTPSettings()

    assert settings.get_settings_name() == "otp"
    assert settings.cooldown_seconds == 300
    assert settings.expiry_seconds == 900
    assert settings.max_attempts_per_day == 5


def test_otp_settings_config_and_secret_keys() -> None:
    settings = OTPSettings()

    assert settings.get_configs_secrets() == {
        "configs": [
            "otp-cooldown-seconds",
            "otp-expiry-seconds",
            "otp-max-attempts-per-day",
        ],
        "secrets": [],
    }


def test_email_provider_settings_defaults_and_name() -> None:
    settings = EmailProviderSettings()

    assert settings.get_settings_name() == "emailproviders"
    assert settings.provider == "console"
    assert settings.resend_api_key is None
    assert settings.smtp_host is None
    assert settings.smtp_port == 587
    assert settings.smtp_username is None
    assert settings.smtp_password is None
    assert settings.smtp_use_tls is True


def test_email_provider_settings_config_and_secret_keys() -> None:
    settings = EmailProviderSettings()

    assert settings.get_configs_secrets() == {
        "configs": [
            "emailproviders-provider",
            "emailproviders-smtp-host",
            "emailproviders-smtp-port",
            "emailproviders-smtp-username",
            "emailproviders-smtp-use-tls",
        ],
        "secrets": [
            "emailproviders-resend-api-key",
            "emailproviders-smtp-password",
        ],
    }
