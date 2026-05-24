# Backend Configuration

The backend configuration system lives under `backend/config/settings`. It loads strongly typed Pydantic settings classes, applies environment YAML overrides, and optionally applies local development secrets.

## Settings Schemas

Each settings group is a class that inherits from `SettingsBase` in `backend/config/settings/schemas/base_settings.py`.

A schema should:

- Define default values as Pydantic model fields.
- Use `SecretStr` for secret values.
- Implement `get_settings_name()` to return the YAML namespace for that settings group.
- Be exported from `backend/config/settings/schemas/__init__.py` through `__all__`.

The loader discovers settings classes from `schemas.__all__`, so it does not need to be edited when a new settings class is added.

Example:

```python
from pydantic import SecretStr

from .base_settings import SettingsBase


class ExampleSettings(SettingsBase):
    api_url: str = "https://example.test"
    api_key: SecretStr = SecretStr("local-default")

    @staticmethod
    def get_settings_name() -> str:
        return "example"
```

Then export it:

```python
from .example_settings import ExampleSettings

__all__ = ["AuthSettings", "DatabaseSettings", "ExampleSettings"]
```

## YAML Files

Configuration values are read from `backend/config/values`.

- `dev.yaml` is used by the default `dev` environment.
- `prod.yaml` is used when `SettingsLoader(environment="prod")` is used.
- `secrets.yaml` is only read in the `dev` environment.

If a YAML file is missing, defaults from the settings schema are preserved.

## YAML Key Formats

Both nested and flat YAML keys are supported.

Nested format:

```yaml
auth:
  access-expiration-minutes: 1440
  refresh-expiration-minutes: 43200

db:
  pool-size: 5
  max-overflow: 10
```

Flat format:

```yaml
auth-access-expiration-minutes: 1440
auth-refresh-expiration-minutes: 43200
db-pool-size: 5
db-max-overflow: 10
```

Schema field names use underscores in Python. YAML keys use hyphens and are prefixed by the schema settings name. For example, `auth-access-expiration-minutes` maps to `AuthSettings.access_expiration_minutes`.

## Secrets

Fields annotated as `SecretStr` are treated as secrets by `SettingsBase.get_configs_secrets()`.

In development, secrets can be provided in `backend/config/values/secrets.yaml`:

```yaml
auth:
  secret-key: dev-secret

db:
  url: postgresql+asyncpg://user:password@localhost:5432/devdb
```

In production, `secrets.yaml` is not loaded by `SettingsLoader`; production secrets should come from the deployment environment or secret-management layer.

## Loading Settings

Use the async loader when calling from async application startup code:

```python
from config.settings.settigns_loader import SettingsLoader

settings = await SettingsLoader().load_settings()
auth_settings = settings["AuthSettings"]
```

Use the sync loader when calling from scripts, migrations, or synchronous setup code:

```python
from config.settings.settigns_loader import SettingsLoader

settings = SettingsLoader().load_settings_sync()
database_settings = settings["DatabaseSettings"]
```

Both methods return `dict[str, SettingsBase]` and discover schemas automatically from `schemas.__all__`.

## Adding A New Settings Group

1. Create a new schema class in `backend/config/settings/schemas`.
2. Inherit from `SettingsBase`.
3. Implement `get_settings_name()`.
4. Use `SecretStr` for secret fields.
5. Export the class from `schemas/__init__.py` and add it to `__all__`.
6. Add config values to `dev.yaml` or `prod.yaml` under the schema namespace.
7. Add development-only secret values to `secrets.yaml` when needed.

No changes are required in `SettingsLoader` for new settings groups.
