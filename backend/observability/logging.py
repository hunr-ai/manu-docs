from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

DEFAULT_LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 5

_CONFIGURED = False
_CONFIGURED_SERVICE_NAME: str | None = None
_CONFIGURED_ENVIRONMENT: str | None = None


def add_service_context(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    if _CONFIGURED_SERVICE_NAME is not None:
        event_dict.setdefault("service", _CONFIGURED_SERVICE_NAME)
    if _CONFIGURED_ENVIRONMENT is not None:
        event_dict.setdefault("environment", _CONFIGURED_ENVIRONMENT)
    return event_dict


def configure_logging(
    *,
    service_name: str,
    environment: str = "dev",
    log_dir: Path | str | None = None,
    level: str | int | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> None:
    global _CONFIGURED, _CONFIGURED_ENVIRONMENT, _CONFIGURED_SERVICE_NAME

    log_level = _resolve_log_level(level)
    resolved_log_dir = _resolve_log_dir(log_dir)
    resolved_log_dir.mkdir(parents=True, exist_ok=True)

    _CONFIGURED_SERVICE_NAME = service_name
    _CONFIGURED_ENVIRONMENT = environment

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        add_service_context,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    console_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=_should_use_colors(environment)),
        ],
    )
    file_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers = [
        _make_console_handler(log_level, console_formatter),
        _make_rotating_file_handler(
            resolved_log_dir / "app.log",
            log_level,
            file_formatter,
            max_bytes,
            backup_count,
        ),
        _make_rotating_file_handler(
            resolved_log_dir / "error.log",
            logging.ERROR,
            file_formatter,
            max_bytes,
            backup_count,
        ),
    ]

    _quiet_noisy_loggers(log_level)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def is_logging_configured() -> bool:
    return _CONFIGURED


def reset_logging_for_tests() -> None:
    global _CONFIGURED, _CONFIGURED_ENVIRONMENT, _CONFIGURED_SERVICE_NAME

    logging.getLogger().handlers = []
    logging.getLogger().setLevel(logging.WARNING)
    structlog.reset_defaults()
    _CONFIGURED = False
    _CONFIGURED_ENVIRONMENT = None
    _CONFIGURED_SERVICE_NAME = None


def _resolve_log_level(level: str | int | None) -> int:
    if isinstance(level, int):
        return level

    raw_level = level or os.environ.get("LOG_LEVEL", "INFO")
    resolved_level = logging.getLevelName(raw_level.upper())
    if isinstance(resolved_level, int):
        return resolved_level
    return logging.INFO


def _resolve_log_dir(log_dir: Path | str | None) -> Path:
    if log_dir is not None:
        return Path(log_dir)
    if env_log_dir := os.environ.get("LOG_DIR"):
        return Path(env_log_dir)
    return DEFAULT_LOG_DIR


def _should_use_colors(environment: str) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return environment == "dev" and sys.stderr.isatty()


def _make_console_handler(
    level: int,
    formatter: logging.Formatter,
) -> logging.StreamHandler:
    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(formatter)
    return handler


def _make_rotating_file_handler(
    log_path: Path,
    level: int,
    formatter: logging.Formatter,
    max_bytes: int,
    backup_count: int,
) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(formatter)
    return handler


def _quiet_noisy_loggers(level: int) -> None:
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "temporalio"):
        logger = logging.getLogger(logger_name)
        logger.handlers = []
        logger.propagate = True
        logger.setLevel(level)
