import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TypeVar

from config.settings.schemas import DatabaseSettings, EmailProviderSettings
from config.settings.schemas.base_settings import SettingsBase
from config.settings.settings_loader import get_settings_loader
from db.models import EmailTrack
from emails.email_service import RenderedEmail
from emails.providers.provider_loader import load_email_provider
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from structlog import get_logger
from temporalio import activity
from workflows.dto.emails.send_email_request_dto import (
    EmailTrackStateDTO,
    SendEmailFailureDTO,
    SendEmailProviderResultDTO,
    SendEmailRequestDTO,
)

logger = get_logger(__name__)
RequiredSettings = TypeVar("RequiredSettings", bound=SettingsBase)


def get_required_loaded_settings(
    settings_schema: type[RequiredSettings],
) -> RequiredSettings:
    environment = os.environ.get("ENVIRONMENT", "dev")
    settings_loader = get_settings_loader(environment)
    loaded_settings = settings_loader.load_settings_sync()
    return settings_loader.get_required_settings(loaded_settings, settings_schema)


@asynccontextmanager
async def get_activity_db_session() -> AsyncIterator[AsyncSession]:
    db_settings = get_required_loaded_settings(DatabaseSettings)
    engine = create_async_engine(
        db_settings.url.get_secret_value(),
        pool_size=db_settings.pool_size,
        max_overflow=db_settings.max_overflow,
        pool_pre_ping=True,
    )
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        async with sessionmaker() as session:
            yield session
    finally:
        await engine.dispose()


async def get_email_track(
    db_session: AsyncSession,
    tracking_token: str,
) -> EmailTrack | None:
    result = await db_session.execute(
        select(EmailTrack).where(EmailTrack.tracking_token == tracking_token)
    )
    return result.scalar_one_or_none()


def to_email_track_state(email_track: EmailTrack) -> EmailTrackStateDTO:
    return EmailTrackStateDTO(
        tracking_token=email_track.tracking_token,
        status=email_track.status,
        email_track_id=email_track.id,
    )


@activity.defn
async def create_pending_email_request_activity(
    request: SendEmailRequestDTO,
) -> EmailTrackStateDTO:
    tracking_token = request.require_tracking_token()

    async with get_activity_db_session() as db_session:
        email_track = await get_email_track(db_session, tracking_token)
        if email_track is not None:
            return to_email_track_state(email_track)

        email_track = EmailTrack(
            recipient=request.to,
            subject=request.subject,
            tracking_token=tracking_token,
            status="pending",
        )
        db_session.add(email_track)
        try:
            await db_session.commit()
        except IntegrityError:
            await db_session.rollback()
            email_track = await get_email_track(db_session, tracking_token)
            if email_track is not None:
                return to_email_track_state(email_track)
            raise

        return to_email_track_state(email_track)


@activity.defn
async def send_email_activity(
    request: SendEmailRequestDTO,
) -> SendEmailProviderResultDTO:
    tracking_token = request.require_tracking_token()
    settings = get_required_loaded_settings(EmailProviderSettings)
    provider = load_email_provider(settings)

    if settings.provider == "console" and request.debug_code:
        await logger.ainfo(
            "Console email debug code",
            tracking_token=tracking_token,
            to=request.to,
            debug_code=request.debug_code,
        )

    sent = await provider.send_email(
        RenderedEmail(
            subject=request.subject,
            html_body=request.html_body,
            text_body=request.text_body,
            to=request.to,
            from_email=request.from_email,
        )
    )
    return SendEmailProviderResultDTO(
        tracking_token=tracking_token,
        provider=settings.provider,
        sent=sent,
    )


@activity.defn
async def mark_email_delivered_activity(
    result: SendEmailProviderResultDTO,
) -> EmailTrackStateDTO:
    async with get_activity_db_session() as db_session:
        email_track = await get_email_track(db_session, result.tracking_token)
        if email_track is None:
            raise ValueError("email track not found")

        if email_track.read_at is None:
            email_track.status = "delivered"
        email_track.sent_at = datetime.now(UTC).replace(tzinfo=None)
        await db_session.commit()
        return to_email_track_state(email_track)


@activity.defn
async def mark_email_failed_activity(
    failure: SendEmailFailureDTO,
) -> EmailTrackStateDTO:
    async with get_activity_db_session() as db_session:
        email_track = await get_email_track(db_session, failure.tracking_token)
        if email_track is None:
            raise ValueError("email track not found")

        email_track.status = "failed"
        email_track.failure_reason = failure.failure_reason
        await db_session.commit()
        return to_email_track_state(email_track)
