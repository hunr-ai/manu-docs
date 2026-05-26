import asyncio
import os

from observability.logging import configure_logging
from structlog import get_logger
from temporalio.client import Client
from temporalio.worker import Worker
from workflows.emails.activities.send_email_activity import (
    create_pending_email_request_activity,
    mark_email_delivered_activity,
    mark_email_failed_activity,
    send_email_activity,
)
from workflows.emails.send_email_workflow import SendEmailWorkflow

DEFAULT_EMAIL_TASK_QUEUE = "manudocs-email"

environment = os.environ.setdefault("ENVIRONMENT", "dev")
configure_logging(service_name="manudocs-email-worker", environment=environment)
logger = get_logger(__name__)


async def run_worker() -> None:
    temporal_address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
    task_queue = os.environ.get(
        "TEMPORAL_EMAIL_TASK_QUEUE",
        DEFAULT_EMAIL_TASK_QUEUE,
    )
    await logger.ainfo(
        "Email worker startup started",
        temporal_address=temporal_address,
        temporal_namespace=temporal_namespace,
        task_queue=task_queue,
    )
    client = await Client.connect(temporal_address, namespace=temporal_namespace)
    await logger.ainfo("Temporal client connected")
    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[SendEmailWorkflow],
        activities=[
            create_pending_email_request_activity,
            send_email_activity,
            mark_email_delivered_activity,
            mark_email_failed_activity,
        ],
    )
    await logger.ainfo("Email worker started", task_queue=task_queue)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())
