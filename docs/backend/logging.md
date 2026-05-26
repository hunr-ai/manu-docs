# Backend Logging

The backend uses a shared structlog setup in `backend/observability/logging.py`. It is initialized by the FastAPI process in `backend/main.py` and by the Temporal email worker in `backend/workflows/emails/worker.py`.

## Outputs

In development, logs are rendered to the console with structlog's developer renderer. The same events are also written as JSON lines to rotating files under `backend/logs`:

- `app.log` receives events at the configured log level and above.
- `error.log` receives error events and above.

Runtime log files are ignored by Git.

When the backend runs through Docker Compose, `LOG_DIR` is set to `/var/log/manudocs` and backed by a named Docker volume. This keeps rotating log writes outside the bind-mounted `/app` source tree so Uvicorn reload is not triggered by log file changes.

## Configuration

`configure_logging()` accepts these process-specific values:

- `service_name`: identifies the process emitting logs, such as `manudocs-api` or `manudocs-email-worker`.
- `environment`: identifies the runtime environment and defaults to `dev`.
- `log_dir`: overrides the log file directory.
- `LOG_DIR`: environment variable used as the default log file directory when `log_dir` is omitted.
- `level`: overrides the log level. If omitted, `LOG_LEVEL` is used, then `INFO`.
- `max_bytes` and `backup_count`: control the rotating file handlers.

Every structured log event includes `service`, `environment`, `logger`, `level`, and an ISO timestamp.

## Usage

Use structlog directly in application and worker code:

```python
from structlog import get_logger

logger = get_logger(__name__)

logger.info("Synchronous event", resource_id=resource_id)
await logger.ainfo("Asynchronous event", request_id=request_id)
```

Do not configure logging from inside Temporal workflow code. Workflow definitions must stay deterministic and replay-safe. Configure logging in process entrypoints and activities instead.

## Future Observability

The current JSON file output is intentionally shaped for later ingestion by an OpenTelemetry handler or a self-hosted Grafana stack. That stack is not part of the current backend runtime yet; when added, it should plug into the shared logging module instead of adding one-off handlers throughout the application.
