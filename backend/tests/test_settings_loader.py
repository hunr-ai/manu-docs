import asyncio
from pathlib import Path

import config.settings.settigns_loader as settings_loader_module
from config.settings import schemas
from config.settings.schemas.auth_settings import AuthSettings
from config.settings.schemas.base_settings import SettingsBase
from config.settings.schemas.db_settings import DatabaseSettings
from config.settings.settigns_loader import SettingsLoader
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
    assert loader._get_schemas() == (AuthSettings, DatabaseSettings)
    assert loader._get_schema("AuthSettings") is AuthSettings
    assert loader._get_schema("DatabaseSettings") is DatabaseSettings


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


def test_loader_preserves_defaults_without_yaml(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings_loader_module, "BASE_DIR", tmp_path)

    loaded_settings = load_settings(SettingsLoader())

    auth_settings = loaded_settings["AuthSettings"]
    database_settings = loaded_settings["DatabaseSettings"]
    assert isinstance(auth_settings, AuthSettings)
    assert isinstance(database_settings, DatabaseSettings)
    assert auth_settings.access_expiration_minutes == 60 * 24
    assert auth_settings.secret_key.get_secret_value() == "supersecretkey"
    assert database_settings.pool_size == 5
    assert database_settings.url.get_secret_value().startswith("postgresql+asyncpg://")


def test_loader_applies_dev_config_and_secrets_from_nested_yaml(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings_loader_module, "BASE_DIR", tmp_path)
    write_yaml(
        tmp_path,
        "dev.yaml",
        """
auth:
  access-expiration-minutes: 12
  refresh-expiration-minutes: 34
db:
  pool-size: 7
  max-overflow: 8
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
""",
    )

    loaded_settings = load_settings(SettingsLoader())

    auth_settings = loaded_settings["AuthSettings"]
    database_settings = loaded_settings["DatabaseSettings"]
    assert isinstance(auth_settings, AuthSettings)
    assert isinstance(database_settings, DatabaseSettings)
    assert auth_settings.access_expiration_minutes == 12
    assert auth_settings.refresh_expiration_minutes == 34
    assert isinstance(auth_settings.secret_key, SecretStr)
    assert auth_settings.secret_key.get_secret_value() == "dev-secret"
    assert database_settings.pool_size == 7
    assert database_settings.max_overflow == 8
    assert isinstance(database_settings.url, SecretStr)
    assert (
        database_settings.url.get_secret_value()
        == "postgresql+asyncpg://user:password@localhost:5432/devdb"
    )


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
""",
    )

    loaded_settings = load_settings_sync(SettingsLoader())

    auth_settings = loaded_settings["AuthSettings"]
    database_settings = loaded_settings["DatabaseSettings"]
    assert isinstance(auth_settings, AuthSettings)
    assert isinstance(database_settings, DatabaseSettings)
    assert auth_settings.access_expiration_minutes == 18
    assert auth_settings.secret_key.get_secret_value() == "sync-secret"
    assert database_settings.pool_size == 9
    assert (
        database_settings.url.get_secret_value()
        == "postgresql+asyncpg://user:password@localhost:5432/syncdb"
    )


def test_loader_supports_flat_yaml_keys(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings_loader_module, "BASE_DIR", tmp_path)
    write_yaml(
        tmp_path,
        "dev.yaml",
        """
auth-access-expiration-minutes: 22
db-max-overflow: 11
""",
    )
    write_yaml(
        tmp_path,
        "secrets.yaml",
        """
auth-secret-key: flat-secret
db-url: postgresql+asyncpg://user:password@localhost:5432/flatdb
""",
    )

    loaded_settings = load_settings(SettingsLoader())

    auth_settings = loaded_settings["AuthSettings"]
    database_settings = loaded_settings["DatabaseSettings"]
    assert isinstance(auth_settings, AuthSettings)
    assert isinstance(database_settings, DatabaseSettings)
    assert auth_settings.access_expiration_minutes == 22
    assert auth_settings.secret_key.get_secret_value() == "flat-secret"
    assert database_settings.max_overflow == 11
    assert (
        database_settings.url.get_secret_value()
        == "postgresql+asyncpg://user:password@localhost:5432/flatdb"
    )


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
""",
    )

    loaded_settings = load_settings(SettingsLoader(environment="prod"))

    auth_settings = loaded_settings["AuthSettings"]
    database_settings = loaded_settings["DatabaseSettings"]
    assert isinstance(auth_settings, AuthSettings)
    assert isinstance(database_settings, DatabaseSettings)
    assert auth_settings.access_expiration_minutes == 90
    assert auth_settings.secret_key.get_secret_value() == "supersecretkey"
    assert database_settings.pool_size == 20
    assert database_settings.url.get_secret_value().endswith("manudocsdb")


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
    assert isinstance(auth_settings, AuthSettings)
    assert isinstance(database_settings, DatabaseSettings)
    assert auth_settings.access_expiration_minutes == 5
    assert auth_settings.refresh_expiration_minutes == 60 * 24 * 30
    assert database_settings.pool_size == 5
    assert database_settings.max_overflow == 10


def test_loader_ignores_non_mapping_yaml(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings_loader_module, "BASE_DIR", tmp_path)
    write_yaml(tmp_path, "dev.yaml", "- not\n- a\n- mapping\n")
    write_yaml(tmp_path, "secrets.yaml", "plain-secret-value\n")

    loaded_settings = load_settings_sync(SettingsLoader())

    auth_settings = loaded_settings["AuthSettings"]
    assert isinstance(auth_settings, AuthSettings)
    assert auth_settings.access_expiration_minutes == 60 * 24
    assert auth_settings.secret_key.get_secret_value() == "supersecretkey"
