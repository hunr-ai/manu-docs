import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from typing import Any, TypeVar, cast

import pytest
from config.settings.schemas import EmailProviderSettings
from db.models import EmailTrack
from emails.email_service import RenderedEmail
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.testing import ActivityEnvironment
from workflows.dto.emails.send_email_request_dto import (
    SendEmailFailureDTO,
    SendEmailProviderResultDTO,
    SendEmailRequestDTO,
)
from workflows.emails.activities import send_email_activity as activity_module

AsyncReturn = TypeVar("AsyncReturn")


class FakeResult:
    def __init__(self, email_track: EmailTrack | None):
        self.email_track = email_track

    def scalar_one_or_none(self) -> EmailTrack | None:
        return self.email_track


class FakeSession:
    def __init__(self, email_track: EmailTrack | None = None):
        self.email_track = email_track
        self.added: list[EmailTrack] = []
        self.commits = 0
        self.rollbacks = 0
        self.statements: list[object] = []

    async def execute(self, statement: object) -> FakeResult:
        self.statements.append(statement)
        return FakeResult(self.email_track)

    def add(self, email_track: EmailTrack) -> None:
        email_track.id = 42
        self.email_track = email_track
        self.added.append(email_track)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeProvider:
    def __init__(self):
        self.sent_emails: list[RenderedEmail] = []

    async def send_email(self, rendered_email: RenderedEmail) -> bool:
        self.sent_emails.append(rendered_email)
        return True


class FakeLogger:
    def __init__(self):
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def ainfo(self, message: str, **kwargs: object) -> None:
        self.calls.append((message, kwargs))


def run_async(value: Coroutine[Any, Any, AsyncReturn]) -> AsyncReturn:
    return asyncio.run(value)


def run_activity(activity: object, *args: object) -> object:
    async def run_in_activity_environment() -> object:
        environment = ActivityEnvironment()
        return await environment.run(activity, *args)

    return run_async(run_in_activity_environment())


def override_activity_session(
    monkeypatch: pytest.MonkeyPatch,
    session: FakeSession,
) -> None:
    @asynccontextmanager
    async def fake_activity_session() -> AsyncIterator[AsyncSession]:
        yield cast(AsyncSession, session)

    monkeypatch.setattr(
        activity_module, "get_activity_db_session", fake_activity_session
    )


def make_request() -> SendEmailRequestDTO:
    return SendEmailRequestDTO(
        to="user@example.test",
        subject="Login code",
        html_body="<strong>123456</strong>",
        text_body="Your code is 123456.",
        from_email="sender@example.test",
        tracking_token="tracking-token",
        debug_code="123456",
    )


def test_send_email_request_requires_tracking_token() -> None:
    request = SendEmailRequestDTO(
        to="user@example.test",
        subject="Subject",
        html_body="html",
        text_body="text",
    )

    with pytest.raises(ValueError, match="tracking_token is required"):
        request.require_tracking_token()

    assert request.with_tracking_token("token").tracking_token == "token"


def test_create_pending_email_request_creates_email_track(monkeypatch) -> None:
    session = FakeSession()
    override_activity_session(monkeypatch, session)

    state = run_activity(
        activity_module.create_pending_email_request_activity,
        make_request(),
    )

    assert state.tracking_token == "tracking-token"
    assert state.status == "pending"
    assert state.email_track_id == 42
    assert len(session.added) == 1
    assert session.added[0].recipient == "user@example.test"
    assert session.added[0].subject == "Login code"
    assert session.added[0].tracking_token == "tracking-token"
    assert session.commits == 1


def test_create_pending_email_request_is_idempotent(monkeypatch) -> None:
    email_track = EmailTrack(
        recipient="user@example.test",
        subject="Login code",
        tracking_token="tracking-token",
        status="delivered",
    )
    email_track.id = 7
    session = FakeSession(email_track)
    override_activity_session(monkeypatch, session)

    state = run_activity(
        activity_module.create_pending_email_request_activity,
        make_request(),
    )

    assert state.tracking_token == "tracking-token"
    assert state.status == "delivered"
    assert state.email_track_id == 7
    assert session.added == []
    assert session.commits == 0


def test_send_email_activity_loads_provider_and_logs_console_code(monkeypatch) -> None:
    provider = FakeProvider()
    logger = FakeLogger()
    monkeypatch.setattr(activity_module, "logger", logger)
    monkeypatch.setattr(
        activity_module,
        "get_required_loaded_settings",
        lambda settings_schema: EmailProviderSettings(provider="console"),
    )
    monkeypatch.setattr(
        activity_module, "load_email_provider", lambda settings: provider
    )

    result = run_activity(activity_module.send_email_activity, make_request())

    assert result == SendEmailProviderResultDTO(
        tracking_token="tracking-token",
        provider="console",
        sent=True,
    )
    assert provider.sent_emails == [
        RenderedEmail(
            subject="Login code",
            html_body="<strong>123456</strong>",
            text_body="Your code is 123456.",
            to="user@example.test",
            from_email="sender@example.test",
        )
    ]
    assert logger.calls == [
        (
            "Console email debug code",
            {
                "tracking_token": "tracking-token",
                "to": "user@example.test",
                "debug_code": "123456",
            },
        )
    ]


def test_mark_email_delivered_updates_tracking_record(monkeypatch) -> None:
    email_track = EmailTrack(
        recipient="user@example.test",
        subject="Login code",
        tracking_token="tracking-token",
        status="pending",
    )
    email_track.id = 9
    session = FakeSession(email_track)
    override_activity_session(monkeypatch, session)

    state = run_activity(
        activity_module.mark_email_delivered_activity,
        SendEmailProviderResultDTO(
            tracking_token="tracking-token",
            provider="console",
            sent=True,
        ),
    )

    assert state.status == "delivered"
    assert state.email_track_id == 9
    assert email_track.status == "delivered"
    assert email_track.sent_at is not None
    assert session.commits == 1


def test_mark_email_failed_records_failure_reason(monkeypatch) -> None:
    email_track = EmailTrack(
        recipient="user@example.test",
        subject="Login code",
        tracking_token="tracking-token",
        status="pending",
    )
    session = FakeSession(email_track)
    override_activity_session(monkeypatch, session)

    state = run_activity(
        activity_module.mark_email_failed_activity,
        SendEmailFailureDTO(
            tracking_token="tracking-token",
            failure_reason="provider error",
        ),
    )

    assert state.status == "failed"
    assert email_track.status == "failed"
    assert email_track.failure_reason == "provider error"
    assert session.commits == 1
