import asyncio
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, TypeVar

from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from workflows.dto.emails.send_email_request_dto import (
    EmailTrackStateDTO,
    SendEmailFailureDTO,
    SendEmailProviderResultDTO,
    SendEmailRequestDTO,
    SendEmailResultDTO,
)
from workflows.emails.send_email_workflow import (
    EMAIL_ACTIVITY_RETRY_POLICY,
    SendEmailWorkflow,
)

AsyncReturn = TypeVar("AsyncReturn")


def run_async(value: Coroutine[Any, Any, AsyncReturn]) -> AsyncReturn:
    return asyncio.run(value)


def make_request(tracking_token: str | None = "tracking-token") -> SendEmailRequestDTO:
    return SendEmailRequestDTO(
        to="user@example.test",
        subject="Login code",
        html_body="<strong>123456</strong>",
        text_body="Your code is 123456.",
        from_email="sender@example.test",
        tracking_token=tracking_token,
        debug_code="123456",
    )


async def execute_send_email_workflow(
    request: SendEmailRequestDTO,
    activities: list[Callable[..., Awaitable[object]]],
    workflow_id: str = "workflow-token",
) -> SendEmailResultDTO:
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        task_queue_name = str(uuid.uuid4())
        async with Worker(
            environment.client,
            task_queue=task_queue_name,
            workflows=[SendEmailWorkflow],
            activities=activities,
        ):
            return await environment.client.execute_workflow(
                SendEmailWorkflow.run,
                request,
                id=workflow_id,
                task_queue=task_queue_name,
            )


def test_send_email_workflow_uses_workflow_id_for_tracking_token() -> None:
    calls: list[tuple[str, object]] = []

    @activity.defn(name="create_pending_email_request_activity")
    async def create_pending_email_request_mock(
        request: SendEmailRequestDTO,
    ) -> EmailTrackStateDTO:
        calls.append(("create_pending_email_request_activity", request))
        return EmailTrackStateDTO(
            tracking_token=request.require_tracking_token(),
            status="pending",
            email_track_id=3,
        )

    @activity.defn(name="send_email_activity")
    async def send_email_mock(
        request: SendEmailRequestDTO,
    ) -> SendEmailProviderResultDTO:
        calls.append(("send_email_activity", request))
        return SendEmailProviderResultDTO(
            tracking_token=request.require_tracking_token(),
            provider="console",
            sent=True,
        )

    @activity.defn(name="mark_email_delivered_activity")
    async def mark_email_delivered_mock(
        result: SendEmailProviderResultDTO,
    ) -> EmailTrackStateDTO:
        calls.append(("mark_email_delivered_activity", result))
        return EmailTrackStateDTO(
            tracking_token=result.tracking_token,
            status="delivered",
            email_track_id=3,
        )

    result = run_async(
        execute_send_email_workflow(
            make_request(tracking_token=None),
            [
                create_pending_email_request_mock,
                send_email_mock,
                mark_email_delivered_mock,
            ],
        )
    )

    assert result.tracking_token == "workflow-token"
    assert result.status == "delivered"
    assert result.provider == "console"
    assert result.sent is True
    assert [call[0] for call in calls] == [
        "create_pending_email_request_activity",
        "send_email_activity",
        "mark_email_delivered_activity",
    ]
    assert calls[0][1].tracking_token == "workflow-token"


def test_send_email_workflow_skips_send_for_delivered_tracking_record() -> None:
    calls: list[str] = []

    @activity.defn(name="create_pending_email_request_activity")
    async def create_pending_email_request_mock(
        request: SendEmailRequestDTO,
    ) -> EmailTrackStateDTO:
        calls.append("create_pending_email_request_activity")
        return EmailTrackStateDTO(
            tracking_token=request.require_tracking_token(),
            status="delivered",
            email_track_id=7,
        )

    result = run_async(
        execute_send_email_workflow(
            make_request(),
            [create_pending_email_request_mock],
        )
    )

    assert result.tracking_token == "tracking-token"
    assert result.status == "delivered"
    assert result.sent is True
    assert result.email_track_id == 7
    assert calls == ["create_pending_email_request_activity"]


def test_send_email_workflow_marks_provider_false_as_failed() -> None:
    calls: list[tuple[str, object]] = []

    @activity.defn(name="create_pending_email_request_activity")
    async def create_pending_email_request_mock(
        request: SendEmailRequestDTO,
    ) -> EmailTrackStateDTO:
        calls.append(("create_pending_email_request_activity", request))
        return EmailTrackStateDTO(
            tracking_token=request.require_tracking_token(),
            status="pending",
            email_track_id=5,
        )

    @activity.defn(name="send_email_activity")
    async def send_email_mock(
        request: SendEmailRequestDTO,
    ) -> SendEmailProviderResultDTO:
        calls.append(("send_email_activity", request))
        return SendEmailProviderResultDTO(
            tracking_token=request.require_tracking_token(),
            provider="console",
            sent=False,
        )

    @activity.defn(name="mark_email_failed_activity")
    async def mark_email_failed_mock(
        failure: SendEmailFailureDTO,
    ) -> EmailTrackStateDTO:
        calls.append(("mark_email_failed_activity", failure))
        assert failure.failure_reason == "email provider returned false"
        return EmailTrackStateDTO(
            tracking_token=failure.tracking_token,
            status="failed",
            email_track_id=5,
        )

    result = run_async(
        execute_send_email_workflow(
            make_request(),
            [
                create_pending_email_request_mock,
                send_email_mock,
                mark_email_failed_mock,
            ],
        )
    )

    assert result.tracking_token == "tracking-token"
    assert result.status == "failed"
    assert result.provider == "console"
    assert result.sent is False
    assert [call[0] for call in calls] == [
        "create_pending_email_request_activity",
        "send_email_activity",
        "mark_email_failed_activity",
    ]


def test_email_workflow_limits_activity_retries() -> None:
    assert EMAIL_ACTIVITY_RETRY_POLICY.maximum_attempts == 4
