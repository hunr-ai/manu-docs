from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import cast

from db.models import EmailTrack
from emails.router import get_db_session, router
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class FakeResult:
    email_track: EmailTrack | None

    def scalar_one_or_none(self) -> EmailTrack | None:
        return self.email_track


class FakeSession:
    def __init__(self, email_track: EmailTrack | None):
        self.email_track = email_track
        self.commits = 0
        self.statements: list[object] = []

    async def execute(self, statement: object) -> FakeResult:
        self.statements.append(statement)
        return FakeResult(self.email_track)

    async def commit(self) -> None:
        self.commits += 1


def create_test_client(session: FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(router)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield cast(AsyncSession, session)

    app.dependency_overrides[get_db_session] = override_get_db_session
    return TestClient(app)


def test_tracking_pixel_marks_unread_email_track_as_read() -> None:
    email_track = EmailTrack(
        recipient="user@example.test",
        subject="Subject",
        tracking_token="known-token",
        status="sent",
    )
    session = FakeSession(email_track)
    client = create_test_client(session)

    response = client.get("/emails/tracking/known-token.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert (
        response.headers["cache-control"]
        == "no-store, no-cache, must-revalidate, max-age=0"
    )
    assert response.content.startswith(b"\x89PNG")
    assert email_track.status == "read"
    assert email_track.read_at is not None
    assert session.commits == 1


def test_tracking_pixel_does_not_rewrite_already_read_email_track() -> None:
    email_track = EmailTrack(
        recipient="user@example.test",
        subject="Subject",
        tracking_token="known-token",
        status="read",
    )
    email_track.read_at = "already-read"  # type: ignore[assignment]
    session = FakeSession(email_track)
    client = create_test_client(session)

    response = client.get("/emails/tracking/known-token.png")

    assert response.status_code == 200
    assert email_track.read_at == "already-read"
    assert session.commits == 0


def test_tracking_pixel_returns_png_for_unknown_token() -> None:
    session = FakeSession(None)
    client = create_test_client(session)

    response = client.get("/emails/tracking/unknown-token.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")
    assert session.commits == 0


def test_tracking_template_renders_pixel_snippet() -> None:
    session = FakeSession(None)
    client = create_test_client(session)

    response = client.get("/emails/tracking/token/template")

    assert response.status_code == 200
    assert response.json() == {
        "html": (
            '<img src="/emails/tracking/token.png" alt="" width="1" height="1" '
            'style="display:none;width:1px;height:1px" />'
        )
    }


def test_tracking_webhook_updates_known_email_track() -> None:
    email_track = EmailTrack(
        recipient="user@example.test",
        subject="Subject",
        tracking_token="known-token",
        status="sent",
    )
    session = FakeSession(email_track)
    client = create_test_client(session)

    response = client.post(
        "/emails/tracking/webhook",
        json={
            "tracking_token": "known-token",
            "status": "failed",
            "provider_message_id": "message-1",
            "failure_reason": "bounced",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "failed", "tracking_token": "known-token"}
    assert email_track.status == "failed"
    assert email_track.provider_message_id == "message-1"
    assert email_track.failure_reason == "bounced"
    assert session.commits == 1


def test_tracking_webhook_sets_read_at_for_read_status() -> None:
    email_track = EmailTrack(
        recipient="user@example.test",
        subject="Subject",
        tracking_token="known-token",
        status="sent",
    )
    session = FakeSession(email_track)
    client = create_test_client(session)

    response = client.post(
        "/emails/tracking/webhook",
        json={"tracking_token": "known-token", "status": "read"},
    )

    assert response.status_code == 200
    assert email_track.status == "read"
    assert email_track.read_at is not None


def test_tracking_webhook_returns_404_for_unknown_token() -> None:
    session = FakeSession(None)
    client = create_test_client(session)

    response = client.post(
        "/emails/tracking/webhook",
        json={"tracking_token": "unknown-token", "status": "read"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "email track not found"}
    assert session.commits == 0
