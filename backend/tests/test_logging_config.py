import asyncio
import json
import logging
from collections.abc import Coroutine
from typing import Any, TypeVar

from observability import logging as logging_config
from structlog import get_logger

AsyncReturn = TypeVar("AsyncReturn")


def run_async(value: Coroutine[Any, Any, AsyncReturn]) -> AsyncReturn:
    return asyncio.run(value)


def teardown_function() -> None:
    logging_config.reset_logging_for_tests()


def read_json_lines(log_path) -> list[dict[str, object]]:
    return [json.loads(line) for line in log_path.read_text().splitlines()]


def test_configure_logging_writes_structured_rotating_files(tmp_path) -> None:
    logging_config.configure_logging(
        service_name="test-service",
        environment="test",
        log_dir=tmp_path,
    )

    logger = get_logger("tests.logging")
    logger.info("hello", answer=42)
    logger.error("boom", failure=True)

    app_events = read_json_lines(tmp_path / "app.log")
    error_events = read_json_lines(tmp_path / "error.log")

    assert [event["event"] for event in app_events] == ["hello", "boom"]
    assert app_events[0]["service"] == "test-service"
    assert app_events[0]["environment"] == "test"
    assert app_events[0]["logger"] == "tests.logging"
    assert app_events[0]["level"] == "info"
    assert app_events[0]["answer"] == 42
    assert error_events[0]["event"] == "boom"
    assert error_events[0]["failure"] is True


def test_configure_logging_uses_log_dir_environment_variable(
    tmp_path,
    monkeypatch,
) -> None:
    configured_log_dir = tmp_path / "env-logs"
    monkeypatch.setenv("LOG_DIR", str(configured_log_dir))

    logging_config.configure_logging(
        service_name="test-service",
        environment="test",
    )

    get_logger("tests.logging").info("from-env-log-dir")

    app_events = read_json_lines(configured_log_dir / "app.log")

    assert app_events[0]["event"] == "from-env-log-dir"
    assert app_events[0]["service"] == "test-service"


def test_configure_logging_replaces_handlers_without_duplicates(tmp_path) -> None:
    logging_config.configure_logging(
        service_name="first-service",
        environment="test",
        log_dir=tmp_path / "first",
    )
    first_handlers = logging.getLogger().handlers

    logging_config.configure_logging(
        service_name="second-service",
        environment="test",
        log_dir=tmp_path / "second",
    )
    second_handlers = logging.getLogger().handlers

    assert len(first_handlers) == 3
    assert len(second_handlers) == 3
    assert first_handlers != second_handlers

    get_logger("tests.logging").info("after-reconfigure")
    app_events = read_json_lines(tmp_path / "second" / "app.log")

    assert app_events[0]["service"] == "second-service"
    assert app_events[0]["event"] == "after-reconfigure"


def test_configured_logger_supports_async_methods(tmp_path) -> None:
    logging_config.configure_logging(
        service_name="async-service",
        environment="test",
        log_dir=tmp_path,
    )

    async def write_log() -> None:
        logger = get_logger("tests.async")
        await logger.ainfo("async hello", request_id="req-1")

    run_async(write_log())

    app_events = read_json_lines(tmp_path / "app.log")

    assert app_events[0]["event"] == "async hello"
    assert app_events[0]["request_id"] == "req-1"
    assert app_events[0]["service"] == "async-service"
