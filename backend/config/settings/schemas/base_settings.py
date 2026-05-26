from typing import get_args

from pydantic import BaseModel, SecretStr


class SettingsBase(BaseModel):
    def get_settings_name(self) -> str:
        raise NotImplementedError("Subclasses must implement get_settings_name()")

    def _get_append_field_name(self, field_name: str, settings_name: str) -> str:
        return f"{settings_name}-{field_name}".replace("_", "-")

    def _is_secret_field(self, annotation: object) -> bool:
        return annotation is SecretStr or SecretStr in get_args(annotation)

    def get_configs_secrets(self) -> dict:
        defined_settings = {"configs": [], "secrets": []}
        defined_fields = self.__class__.model_fields.items()
        settings_name = self.get_settings_name()
        for field_name, field_info in defined_fields:
            is_secret = self._is_secret_field(field_info.annotation)
            if not is_secret:
                defined_settings["configs"].append(
                    self._get_append_field_name(field_name, settings_name)
                )
            else:
                defined_settings["secrets"].append(
                    self._get_append_field_name(field_name, settings_name)
                )
        return defined_settings
