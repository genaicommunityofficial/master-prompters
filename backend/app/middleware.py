"""HTTP middleware: structured request logging + durable DB request-logging.

Every request is measured (latency) and written to `pc_request_logs` (checkbox
via the service role) so the admin monitor can show live traffic. Writing to the
DB is fire-and-forget and must never block or fail the request.
"""

from __future__ import annotations

import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.services import request_log_service
from app.utils.logging_utils import bind_request, configure_logging, log, unbind_request

_SKIP_LOG_PATHS = {"/health", "/metrics"}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        request_id = bind_request()
        # If the user already holds a participant JWT, surface it in logs.
        auth = request.headers.get("authorization", "")
        participant_id = ""
        if auth.lower().startswith("bearer "):
            pass  # Decode done by endpoints; keep middleware cheap.

        status = 500
        latency_ms = 0
        path = request.url.path
        try:
            response = await call_next(request)
            status = response.status_code
            latency_ms = int((time.perf_counter() - start) * 1000)
            return response
        finally:
            latency_ms = latency_ms or int((time.perf_counter() - start) * 1000)
            method = request.method
            log.info(
                "http_request",
                method=method,
                path=path,
                status=status,
                latency_ms=latency_ms,
                ip=request.client.host if request.client else None,
            )
            if settings.request_log_enabled and path not in _SKIP_LOG_PATHS:
                try:
                    request_log_service.log_request(
                        request_id=request_id,
                        method=method,
                        path=path,
                        status=status,
                        latency_ms=latency_ms,
                        ip=request.client.host if request.client else None,
                        participant_id=participant_id,
                    )
                except Exception:  # noqa: BLE001
                    # Never let logging break the request.
                    log.warning("request_log_failed", path=path)
            unbind_request()


def setup(app) -> None:
    configure_logging(settings.log_level)
    app.add_middleware(RequestLoggingMiddleware)