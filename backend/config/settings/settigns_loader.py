from pathlib import Path
from typing import Any, Literal

import aiofiles
import yaml
from pydantic import SecretStr

from . import schemas
from .schemas.base_settings import SettingsBase

SettingsSchema = type[SettingsBase]


BASE_DIR = Path(__file__).parent.parent / "values"


class SettingsLoader:
    def __init__(self, environment: Literal["dev", "prod"] = "dev"):
        self.all_settings: dict[str, SettingsSchema] = {
            setting_name: getattr(schemas, setting_name)
            for setting_name in schemas.__all__
        }
        self._env = environment

    def is_dev(self) -> bool:
        return self._env == "dev"

    def _get_schemas(self) -> tuple[SettingsSchema, ...]:
        return tuple(self.all_settings.values())

    def _get_schema(self, name: str) -> SettingsSchema:
        return self.all_settings[name]

    def _get_yaml_value(
        self, data: dict[str, Any], settings_name: str, setting_key: str
    ) -> Any:
        field_key = setting_key.removeprefix(f"{settings_name}-")
        if setting_key in data:
            return data[setting_key]

        nested_data = data.get(settings_name, {})
        if isinstance(nested_data, dict) and field_key in nested_data:
            return nested_data[field_key]

        return None

    def _get_field_name(self, settings_name: str, setting_key: str) -> str:
        return setting_key.removeprefix(f"{settings_name}-").replace("-", "_")

    def _parse_yaml(self, yaml_content: str) -> dict[str, Any]:
        loaded_yaml = yaml.safe_load(yaml_content) or {}
        if isinstance(loaded_yaml, dict):
            return loaded_yaml
        return {}

    def _load_yaml(self, yaml_file_path: Path) -> dict[str, Any]:
        if yaml_file_path.exists():
            return self._parse_yaml(yaml_file_path.read_text(encoding="utf-8"))
        return {}

    async def _load_yaml_async(self, yaml_file_path: Path) -> dict[str, Any]:
        if yaml_file_path.exists():
            async with aiofiles.open(yaml_file_path, mode="r") as f:
                return self._parse_yaml(await f.read())
        return {}

    def _build_settings(
        self, config_data: dict[str, Any], secrets_data: dict[str, Any]
    ) -> dict[str, SettingsBase]:
        loaded_settings: dict[str, SettingsBase] = {}
        for setting, schema in self.all_settings.items():
            schema = schema()
            configs_secrets = schema.get_configs_secrets()

            for config in configs_secrets["configs"]:
                settings_name = schema.get_settings_name()
                config_field_name = self._get_field_name(settings_name, config)
                config_value = self._get_yaml_value(config_data, settings_name, config)
                if config_value is not None:
                    setattr(schema, config_field_name, config_value)

            for secret in configs_secrets["secrets"]:
                settings_name = schema.get_settings_name()
                secret_field_name = self._get_field_name(settings_name, secret)
                secret_value = self._get_yaml_value(secrets_data, settings_name, secret)
                if secret_value is not None:
                    setattr(schema, secret_field_name, SecretStr(secret_value))

            loaded_settings[setting] = schema

        return loaded_settings

    def load_settings_sync(self) -> dict[str, SettingsBase]:
        config_data = self._load_yaml(BASE_DIR / f"{self._env}.yaml")
        secrets_data = (
            self._load_yaml(BASE_DIR / "secrets.yaml") if self.is_dev() else {}
        )

        return self._build_settings(config_data, secrets_data)

    async def load_settings(self) -> dict[str, SettingsBase]:
        config_data = await self._load_yaml_async(BASE_DIR / f"{self._env}.yaml")
        secrets_data = (
            await self._load_yaml_async(BASE_DIR / "secrets.yaml")
            if self.is_dev()
            else {}
        )

        return self._build_settings(config_data, secrets_data)
