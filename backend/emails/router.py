from collections.abc import AsyncIterator
from datetime import UTC, datetime

from db.get_session import get_db_session
from db.models import EmailTrack
from emails.email_service import EmailService
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/emails", tags=["emails"])

TRANSPARENT_PIXEL = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360000002000100ffff03000006000557bfab9d00000000"
    "49454e44ae426082"
)
PIXEL_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
}


class TrackingWebhookRequest(BaseModel):
    tracking_token: str
    status: str | None = None
    provider_message_id: str | None = None
    failure_reason: str | None = None


async def get_email_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> AsyncIterator[EmailService]:
    yield EmailService(db_session)


async def get_email_track(
    db_session: AsyncSession,
    tracking_token: str,
) -> EmailTrack | None:
    result = await db_session.execute(
        select(EmailTrack).where(EmailTrack.tracking_token == tracking_token)
    )
    return result.scalar_one_or_none()


@router.get("/tracking/{tracking_token}.png")
async def mark_email_read(
    tracking_token: str,
    db_session: AsyncSession = Depends(get_db_session),
) -> Response:
    email_track = await get_email_track(db_session, tracking_token)
    if email_track is not None and email_track.read_at is None:
        email_track.read_at = datetime.now(UTC).replace(tzinfo=None)
        email_track.status = "read"
        await db_session.commit()

    return Response(
        content=TRANSPARENT_PIXEL,
        media_type="image/png",
        headers=PIXEL_HEADERS,
    )


@router.get("/tracking/{tracking_token}/template")
async def render_tracking_template(
    tracking_token: str,
    email_service: EmailService = Depends(get_email_service),
) -> dict[str, str]:
    return {
        "html": email_service.render_tracking_pixel(
            f"/emails/tracking/{tracking_token}.png"
        )
    }


@router.post("/tracking/webhook")
async def update_email_tracking_status(
    request: TrackingWebhookRequest,
    db_session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    email_track = await get_email_track(db_session, request.tracking_token)
    if email_track is None:
        raise HTTPException(status_code=404, detail="email track not found")

    if request.status is not None:
        email_track.status = request.status
        if request.status == "read" and email_track.read_at is None:
            email_track.read_at = datetime.now(UTC).replace(tzinfo=None)
    if request.provider_message_id is not None:
        email_track.provider_message_id = request.provider_message_id
    if request.failure_reason is not None:
        email_track.failure_reason = request.failure_reason

    await db_session.commit()

    return {"status": email_track.status, "tracking_token": email_track.tracking_token}
