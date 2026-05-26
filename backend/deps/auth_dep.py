import os
from collections.abc import AsyncIterator
from typing import Annotated

from auth.auth_service import AuthService
from config.settings.schemas import AuthSettings
from db.get_session import get_db_session
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client
from utils.otp_utils import OTPUtil, get_otp_util

from deps.settings_dep import get_required_settings
from deps.temporal_dep import get_temporal_client

DEFAULT_AUTH_TASK_QUEUE = "manudocs-email"


async def get_auth_settings(request: Request) -> AuthSettings:
    return await get_required_settings(request, AuthSettings)


def get_auth_task_queue() -> str:
    return os.environ.get("TEMPORAL_EMAIL_TASK_QUEUE", DEFAULT_AUTH_TASK_QUEUE)


async def get_auth_service(
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    otp_util: Annotated[OTPUtil, Depends(get_otp_util)],
    auth_settings: Annotated[AuthSettings, Depends(get_auth_settings)],
    temporal_client: Annotated[Client, Depends(get_temporal_client)],
    task_queue: Annotated[str, Depends(get_auth_task_queue)],
) -> AsyncIterator[AuthService]:
    yield AuthService(
        db_session=db_session,
        otp_util=otp_util,
        auth_settings=auth_settings,
        temporal_client=temporal_client,
        task_queue=task_queue,
    )
