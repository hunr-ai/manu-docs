import asyncio
from pathlib import Path

import config.settings.settings_loader as settings_loader_module
import pytest
from config.settings import schemas
from config.settings.schemas.auth_settings import AuthSettings
from config.settings.schemas.base_settings import SettingsBase
from config.settings.schemas.db_settings import DatabaseSettings
from config.settings.schemas.email_provider_settings import EmailProviderSettings
from config.settings.schemas.otp_settings import OTPSettings
from config.settings.schemas.redis_settings import RedisSettings
from config.settings.settings_loader import SettingsLoader
from pydantic import SecretStr


def load_settings(loader: SettingsLoader) -> dict[str, SettingsBase]:
    return asyncio.run(loader.load_settings())


def load_settings_sync(loader: SettingsLoader) -> dict[str, SettingsBase]:
    return loader.load_settings_sync()


def write_yaml(config_dir: Path, filename: str, contents: str) -> None:
    (config_dir / filename).write_text(contents, encoding="utf-8")


def test_loader_discovers_schema_classes() -> None:
    loader = SettingsLoader()

    assert loader.is_dev() is True
    assert loader.all_settings == {
        setting_name: getattr(schemas, setting_name) for setting_name in schemas.__all__
    }
    assert loader._get_schemas() == (
        AuthSettings,
        DatabaseSettings,
        OTPSettings,
        RedisSettings,
        EmailProviderSettings,
    )
    assert loader._get_schema("AuthSettings") is AuthSettings
    assert loader._get_schema("DatabaseSettings") is DatabaseSettings
    assert loader._get_schema("OTPSettings") is OTPSettings
    assert loader._get_schema("RedisSettings") is RedisSettings
    assert loader._get_schema("EmailProviderSettings") is EmailProviderSettings


def test_loader_identifies_prod_environment() -> None:
    loader = SettingsLoader(environment="prod")

    assert loader.is_dev() is False


def test_loader_helpers_resolve_nested_and_flat_yaml_keys() -> None:
    loader = SettingsLoader()
    data = {
        "auth": {"access-expiration-minutes": 15},
        "auth-refresh-expiration-minutes": 30,
    }

    assert (
        loader._get_field_name("auth", "auth-access-expiration-minutes")
        == "access_expiration_minutes"
    )
    assert loader._get_yaml_value(data, "auth", "auth-access-expiration-minutes") == 15
    assert loader._get_yaml_value(data, "auth", "auth-refresh-expiration-minutes") == 30
    assert loader._get_yaml_value(data, "auth", "auth-missing") is None


def test_loader_get_required_settings_returns_typed_schema() -> None:
    loader = SettingsLoader()
    loaded_settings = {
        "AuthSettings": AuthSettings(),
        "DatabaseSettings": DatabaseSettings(),
        "EmailProviderSettings": EmailProviderSettings(provider="smtp"),
        "OTPSettings": OTPSettings(),
        "RedisSettings": RedisSettings(max_connections=42),
    }

    redis_settings = loader.get_required_settings(loaded_settings, RedisSettings)

    assert redis_settings.max_connections == 42


@pytest.mark.parametrize(
    "loaded_settings",
    [
        {},
        {"RedisSettings": AuthSettings()},
    ],
)
def test_loader_get_required_settings_rejects_missing_or_wrong_schema(
    loaded_settings: dict[str, SettingsBase],
) -> None:
    loader = SettingsLoader()

    with pytest.raises(TypeError, match="RedisSettings schema was not loaded"):
        loader.get_required_settings(loaded_settings, RedisSettings)


def test_loader_preserves_defaults_without_yaml(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings_loader_module, "BASE_DIR", tmp_path)

    loaded_settings = load_settings(SettingsLoader())

    auth_settings = loaded_settings["AuthSettings"]
    database_settings = loaded_settings["DatabaseSettings"]
    email_provider_settings = loaded_settings["EmailProviderSettings"]
    otp_settings = loaded_settings["OTPSettings"]
    redis_settings = loaded_settings["RedisSettings"]
    assert isinstance(auth_settings, AuthSettings)
    assert isinstance(database_settings, DatabaseSettings)
    assert isinstance(email_provider_settings, EmailProviderSettings)
    assert isinstance(otp_settings, OTPSettings)
    assert isinstance(redis_settings, RedisSettings)
    assert auth_settings.access_expiration_minutes == 60 * 24
    assert auth_settings.secret_key.get_secret_value() == "supersecretkey"
    assert auth_settings.jwt_algorithm == "HS256"
    assert auth_settings.jwt_issuer == "manudocs"
    assert auth_settings.access_token_audience == "manudocs-api"
    assert auth_settings.refresh_token_audience == "manudocs-auth"
    assert auth_settings.access_token_scope == "auth:access"
    assert auth_settings.refresh_token_scope == "auth:refresh"
    assert database_settings.pool_size == 5
    assert database_settings.url.get_secret_value().startswith("postgresql+asyncpg://")
    assert email_provider_settings.provider == "console"
    assert email_provider_settings.resend_api_key is None
    assert email_provider_settings.smtp_host is None
    assert email_provider_settings.smtp_port == 587
    assert email_provider_settings.smtp_username is None
    assert email_provider_settings.smtp_password is None
    assert email_provider_settings.smtp_use_tls is True
    assert otp_settings.cooldown_seconds == 300
    assert otp_settings.expiry_seconds == 900
    assert otp_settings.max_attempts_per_day == 5
    assert redis_settings.max_connections == 10
    assert redis_settings.url.get_secret_value() == "redis://localhost:6379/0"


def test_loader_applies_dev_config_and_secrets_from_nested_yaml(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings_loader_module, "BASE_DIR", tmp_path)
    write_yaml(
        tmp_path,
        "dev.yaml",
        """
auth:
    jwt-issuer: test-issuer
    access-token-audience: test-api
    access-expiration-minutes: 12
    refresh-expiration-minutes: 34
db:
  pool-size: 7
  max-overflow: 8
redis:
    max-connections: 25
emailproviders:
    provider: smtp
    smtp-host: smtp.example.test
    smtp-port: 465
    smtp-username: dev-user
    smtp-use-tls: false
""",
    )
    write_yaml(
        tmp_path,
        "secrets.yaml",
        """
auth:
  secret-key: dev-secret
db:
  url: postgresql+asyncpg://user:password@localhost:5432/devdb
redis:
    url: redis://localhost:8379/1
emailproviders:
    resend-api-key: resend-dev-secret
    smtp-password: smtp-dev-secret
""",
    )

    loaded_settings = load_settings(SettingsLoader())

    auth_settings = loaded_settings["AuthSettings"]
    database_settings = loaded_settings["DatabaseSettings"]
    email_provider_settings = loaded_settings["EmailProviderSettings"]
    redis_settings = loaded_settings["RedisSettings"]
    assert isinstance(auth_settings, AuthSettings)
    assert isinstance(database_settings, DatabaseSettings)
    assert isinstance(email_provider_settings, EmailProviderSettings)
    assert isinstance(redis_settings, RedisSettings)
    assert auth_settings.access_expiration_minutes == 12
    assert auth_settings.refresh_expiration_minutes == 34
    assert auth_settings.jwt_issuer == "test-issuer"
    assert auth_settings.access_token_audience == "test-api"
    assert isinstance(auth_settings.secret_key, SecretStr)
    assert auth_settings.secret_key.get_secret_value() == "dev-secret"
    assert database_settings.pool_size == 7
    assert database_settings.max_overflow == 8
    assert isinstance(database_settings.url, SecretStr)
    assert (
        database_settings.url.get_secret_value()
        == "postgresql+asyncpg://user:password@localhost:5432/devdb"
    )
    assert email_provider_settings.provider == "smtp"
    assert email_provider_settings.smtp_host == "smtp.example.test"
    assert email_provider_settings.smtp_port == 465
    assert email_provider_settings.smtp_username == "dev-user"
    assert email_provider_settings.smtp_use_tls is False
    assert isinstance(email_provider_settings.resend_api_key, SecretStr)
    assert (
        email_provider_settings.resend_api_key.get_secret_value() == "resend-dev-secret"
    )
    assert isinstance(email_provider_settings.smtp_password, SecretStr)
    assert email_provider_settings.smtp_password.get_secret_value() == "smtp-dev-secret"
    assert redis_settings.max_connections == 25
    assert isinstance(redis_settings.url, SecretStr)
    assert redis_settings.url.get_secret_value() == "redis://localhost:8379/1"


def test_sync_loader_applies_dev_config_and_secrets_from_nested_yaml(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings_loader_module, "BASE_DIR", tmp_path)
    write_yaml(
        tmp_path,
        "dev.yaml",
        """
auth:
    access-expiration-minutes: 18
db:
    pool-size: 9
redis:
    max-connections: 30
emailproviders:
    provider: smtp
    smtp-host: smtp-sync.example.test
    smtp-port: 2525
    smtp-username: sync-user
""",
    )
    write_yaml(
        tmp_path,
        "secrets.yaml",
        """
auth:
    secret-key: sync-secret
db:
    url: postgresql+asyncpg://user:password@localhost:5432/syncdb
redis:
    url: redis://localhost:8379/2
emailproviders:
    resend-api-key: resend-sync-secret
    smtp-password: smtp-sync-secret
""",
    )

    loaded_settings = load_settings_sync(SettingsLoader())

    auth_settings = loaded_settings["AuthSettings"]
    database_settings = loaded_settings["DatabaseSettings"]
    email_provider_settings = loaded_settings["EmailProviderSettings"]
    redis_settings = loaded_settings["RedisSettings"]
    assert isinstance(auth_settings, AuthSettings)
    assert isinstance(database_settings, DatabaseSettings)
    assert isinstance(email_provider_settings, EmailProviderSettings)
    assert isinstance(redis_settings, RedisSettings)
    assert auth_settings.access_expiration_minutes == 18
    assert auth_settings.secret_key.get_secret_value() == "sync-secret"
    assert database_settings.pool_size == 9
    assert (
        database_settings.url.get_secret_value()
        == "postgresql+asyncpg://user:password@localhost:5432/syncdb"
    )
    assert email_provider_settings.provider == "smtp"
    assert email_provider_settings.smtp_host == "smtp-sync.example.test"
    assert email_provider_settings.smtp_port == 2525
    assert email_provider_settings.smtp_username == "sync-user"
    assert isinstance(email_provider_settings.resend_api_key, SecretStr)
    assert (
        email_provider_settings.resend_api_key.get_secret_value()
        == "resend-sync-secret"
    )
    assert isinstance(email_provider_settings.smtp_password, SecretStr)
    assert (
        email_provider_settings.smtp_password.get_secret_value() == "smtp-sync-secret"
    )
    assert redis_settings.max_connections == 30
    assert redis_settings.url.get_secret_value() == "redis://localhost:8379/2"


def test_loader_supports_flat_yaml_keys(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings_loader_module, "BASE_DIR", tmp_path)
    write_yaml(
        tmp_path,
        "dev.yaml",
        """
auth-access-expiration-minutes: 22
auth-refresh-token-scope: refresh:flat
db-max-overflow: 11
redis-max-connections: 40
emailproviders-provider: smtp
emailproviders-smtp-host: smtp-flat.example.test
emailproviders-smtp-port: 1025
emailproviders-smtp-username: flat-user
emailproviders-smtp-use-tls: false
""",
    )
    write_yaml(
        tmp_path,
        "secrets.yaml",
        """
auth-secret-key: flat-secret
db-url: postgresql+asyncpg://user:password@localhost:5432/flatdb
redis-url: redis://localhost:8379/3
emailproviders-resend-api-key: resend-flat-secret
emailproviders-smtp-password: smtp-flat-secret
""",
    )

    loaded_settings = load_settings(SettingsLoader())

    auth_settings = loaded_settings["AuthSettings"]
    database_settings = loaded_settings["DatabaseSettings"]
    email_provider_settings = loaded_settings["EmailProviderSettings"]
    redis_settings = loaded_settings["RedisSettings"]
    assert isinstance(auth_settings, AuthSettings)
    assert isinstance(database_settings, DatabaseSettings)
    assert isinstance(email_provider_settings, EmailProviderSettings)
    assert isinstance(redis_settings, RedisSettings)
    assert auth_settings.access_expiration_minutes == 22
    assert auth_settings.refresh_token_scope == "refresh:flat"
    assert auth_settings.secret_key.get_secret_value() == "flat-secret"
    assert database_settings.max_overflow == 11
    assert (
        database_settings.url.get_secret_value()
        == "postgresql+asyncpg://user:password@localhost:5432/flatdb"
    )
    assert email_provider_settings.provider == "smtp"
    assert email_provider_settings.smtp_host == "smtp-flat.example.test"
    assert email_provider_settings.smtp_port == 1025
    assert email_provider_settings.smtp_username == "flat-user"
    assert email_provider_settings.smtp_use_tls is False
    assert isinstance(email_provider_settings.resend_api_key, SecretStr)
    assert (
        email_provider_settings.resend_api_key.get_secret_value()
        == "resend-flat-secret"
    )
    assert isinstance(email_provider_settings.smtp_password, SecretStr)
    assert (
        email_provider_settings.smtp_password.get_secret_value() == "smtp-flat-secret"
    )
    assert redis_settings.max_connections == 40
    assert redis_settings.url.get_secret_value() == "redis://localhost:8379/3"


def test_loader_skips_secrets_for_prod(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings_loader_module, "BASE_DIR", tmp_path)
    write_yaml(
        tmp_path,
        "prod.yaml",
        """
auth:
  access-expiration-minutes: 90
db:
  pool-size: 20
redis:
    max-connections: 50
emailproviders:
    provider: smtp
    smtp-host: smtp-prod.example.test
    smtp-username: prod-user
""",
    )
    write_yaml(
        tmp_path,
        "secrets.yaml",
        """
auth:
  secret-key: ignored-prod-secret
db:
  url: postgresql+asyncpg://user:password@localhost:5432/ignored
redis:
    url: redis://localhost:8379/ignored
emailproviders:
    resend-api-key: ignored-resend-secret
    smtp-password: ignored-smtp-secret
""",
    )

    loaded_settings = load_settings(SettingsLoader(environment="prod"))

    auth_settings = loaded_settings["AuthSettings"]
    database_settings = loaded_settings["DatabaseSettings"]
    email_provider_settings = loaded_settings["EmailProviderSettings"]
    redis_settings = loaded_settings["RedisSettings"]
    assert isinstance(auth_settings, AuthSettings)
    assert isinstance(database_settings, DatabaseSettings)
    assert isinstance(email_provider_settings, EmailProviderSettings)
    assert isinstance(redis_settings, RedisSettings)
    assert auth_settings.access_expiration_minutes == 90
    assert auth_settings.secret_key.get_secret_value() == "supersecretkey"
    assert database_settings.pool_size == 20
    assert database_settings.url.get_secret_value().endswith("manudocsdb")
    assert email_provider_settings.provider == "smtp"
    assert email_provider_settings.smtp_host == "smtp-prod.example.test"
    assert email_provider_settings.smtp_username == "prod-user"
    assert email_provider_settings.resend_api_key is None
    assert email_provider_settings.smtp_password is None
    assert redis_settings.max_connections == 50
    assert redis_settings.url.get_secret_value() == "redis://localhost:6379/0"


def test_loader_keeps_defaults_for_partial_yaml(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings_loader_module, "BASE_DIR", tmp_path)
    write_yaml(
        tmp_path,
        "dev.yaml",
        """
auth:
  access-expiration-minutes: 5
""",
    )

    loaded_settings = load_settings(SettingsLoader())

    auth_settings = loaded_settings["AuthSettings"]
    database_settings = loaded_settings["DatabaseSettings"]
    redis_settings = loaded_settings["RedisSettings"]
    assert isinstance(auth_settings, AuthSettings)
    assert isinstance(database_settings, DatabaseSettings)
    assert isinstance(redis_settings, RedisSettings)
    assert auth_settings.access_expiration_minutes == 5
    assert auth_settings.refresh_expiration_minutes == 60 * 24 * 30
    assert database_settings.pool_size == 5
    assert database_settings.max_overflow == 10
    assert redis_settings.max_connections == 10
    assert redis_settings.url.get_secret_value() == "redis://localhost:6379/0"


def test_loader_ignores_non_mapping_yaml(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings_loader_module, "BASE_DIR", tmp_path)
    write_yaml(tmp_path, "dev.yaml", "- not\n- a\n- mapping\n")
    write_yaml(tmp_path, "secrets.yaml", "plain-secret-value\n")

    loaded_settings = load_settings_sync(SettingsLoader())

    auth_settings = loaded_settings["AuthSettings"]
    redis_settings = loaded_settings["RedisSettings"]
    assert isinstance(auth_settings, AuthSettings)
    assert isinstance(redis_settings, RedisSettings)
    assert auth_settings.access_expiration_minutes == 60 * 24
    assert auth_settings.secret_key.get_secret_value() == "supersecretkey"
    assert redis_settings.max_connections == 10
