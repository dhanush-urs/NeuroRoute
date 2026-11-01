import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, Processor


def add_service_name(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    event_dict["service"] = "neuroroute"
    return event_dict


def add_log_level(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    level = method_name.upper()
    if level == "WARN":
        level = "WARNING"
    event_dict["level"] = level
    return event_dict


def configure_logging(log_level: str = "INFO") -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list[Processor] = [
        add_service_name,
        add_log_level,
        timestamper,
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            *shared_processors,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer(colors=True) if sys.stdout.isatty() else structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )


def get_logger(name: str = None) -> structlog.BoundLogger:
    return structlog.get_logger(name)