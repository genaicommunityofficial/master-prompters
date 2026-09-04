"""Structured JSON logging for the application.

Logs are emitted as single-line JSON so they're greppable/traceable in Render.
Sensitive values (prompt text, secrets, keys) are NEVER logged here.
"""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

import structlog

request_id_var: ContextVar[str] = ContextVar("request_id", default="")

_PRE_CONFIGURED = False


def _new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def make_logger(name: str = "app"):
    structlog.configure(**get_config())
    return structlog.get_logger(name)


def get_config() -> dict[str, Any]:
    return {
        "processors": [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        "wrapper_class": structlog.make_filtering_bound_logger(
            getattr(logging, "INFO", logging.INFO)
        ),
        "cache_logger_on_first_use": True,
    }


def configure_logging(level: str = "INFO") -> None:
    global _PRE_CONFIGURED
    if _PRE_CONFIGURED:
        return
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric,
        force=True,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _PRE_CONFIGURED = True


def bind_request(request_id: str | None = None) -> str:
    rid = request_id or _new_request_id()
    request_id_var.set(rid)
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=rid)
    return rid


def unbind_request() -> None:
    structlog.contextvars.clear_contextvars()


# Reusable logger for modules that don't need a fresh one.
log = make_logger()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()