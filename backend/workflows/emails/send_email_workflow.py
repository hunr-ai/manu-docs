from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from workflows.dto.emails.send_email_request_dto import (
    SendEmailFailureDTO,
    SendEmailRequestDTO,
    SendEmailResultDTO,
)

EMAIL_ACTIVITY_RETRY_POLICY = RetryPolicy(maximum_attempts=4)

with workflow.unsafe.imports_passed_through():
    from workflows.emails.activities.send_email_activity import (
        create_pending_email_request_activity,
        mark_email_delivered_activity,
        mark_email_failed_activity,
        send_email_activity,
    )


@workflow.defn
class SendEmailWorkflow:
    @workflow.run
    async def run(self, request: SendEmailRequestDTO) -> SendEmailResultDTO:
        tracking_token = request.tracking_token or workflow.info().workflow_id
        request = request.with_tracking_token(tracking_token)

        pending_track = await workflow.execute_activity(
            create_pending_email_request_activity,
            request,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=EMAIL_ACTIVITY_RETRY_POLICY,
        )

        if pending_track.status in {"delivered", "read"}:
            return SendEmailResultDTO(
                tracking_token=tracking_token,
                status=pending_track.status,
                provider="unknown",
                sent=True,
                email_track_id=pending_track.email_track_id,
            )

        try:
            provider_result = await workflow.execute_activity(
                send_email_activity,
                request,
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=EMAIL_ACTIVITY_RETRY_POLICY,
            )
            if not provider_result.sent:
                failed_track = await workflow.execute_activity(
                    mark_email_failed_activity,
                    SendEmailFailureDTO(
                        tracking_token=tracking_token,
                        failure_reason="email provider returned false",
                    ),
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=EMAIL_ACTIVITY_RETRY_POLICY,
                )
                return SendEmailResultDTO(
                    tracking_token=tracking_token,
                    status=failed_track.status,
                    provider=provider_result.provider,
                    sent=False,
                    email_track_id=failed_track.email_track_id,
                )
        except Exception as exc:
            failed_track = await workflow.execute_activity(
                mark_email_failed_activity,
                SendEmailFailureDTO(
                    tracking_token=tracking_token,
                    failure_reason=str(exc),
                ),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=EMAIL_ACTIVITY_RETRY_POLICY,
            )
            return SendEmailResultDTO(
                tracking_token=tracking_token,
                status=failed_track.status,
                provider="unknown",
                sent=False,
                email_track_id=failed_track.email_track_id,
            )

        delivered_track = await workflow.execute_activity(
            mark_email_delivered_activity,
            provider_result,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=EMAIL_ACTIVITY_RETRY_POLICY,
        )

        return SendEmailResultDTO(
            tracking_token=tracking_token,
            status=delivered_track.status,
            provider=provider_result.provider,
            sent=provider_result.sent,
            email_track_id=delivered_track.email_track_id
            or pending_track.email_track_id,
        )
