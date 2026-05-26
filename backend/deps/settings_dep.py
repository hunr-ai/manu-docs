from config.settings.schemas.base_settings import SettingsBase as RequiredSettings
from fastapi import Request


async def get_required_settings(
    request: Request, settings_schema: type[RequiredSettings]
) -> RequiredSettings:
    settings_loader = request.app.state.settings_loader
    loaded_settings = request.app.state.settings
    return settings_loader.get_required_settings(loaded_settings, settings_schema)
