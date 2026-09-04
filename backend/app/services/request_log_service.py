from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db import db
from app.utils.logging_utils import log

_LOCK = threading.Lock()
_WINDOW_SECONDS = 60
# (epoch_seconds, latency_ms) sliding window for fast, no-DB live aggregates.
_WINDOW: deque[tuple[float, int]] = deque()

tick_now = time.time  # test seam


def log_request(
    *,
    request_id: str,
    method: str,
    path: str,
    status: int,
    latency_ms: int,
    ip: str | None = None,
    participant_id: str = "",
) -> None:
    now = tick_now()
    with _LOCK:
        _WINDOW.append((now, latency_ms))
        cutoff = now - _WINDOW_SECONDS
        while _WINDOW and _WINDOW[0][0] < cutoff:
            _WINDOW.popleft()

    row = {
        "request_id": request_id,
        "method": method,
        "path": (path or "")[:500],
        "status": status,
        "latency_ms": latency_ms,
        "participant_id": participant_id or None,
        "ip": ip,
    }
    try:
        db().table("pc_request_logs").insert(row).execute()
    except Exception as exc:  # noqa: BLE001
        log.warning("request_log_db_write_failed", path=path, error=str(exc)[:200])


def get_recent_logs(since_ts: str | None = None, limit: int = 300) -> list[dict]:
    q = db().table("pc_request_logs").select("*")
    if since_ts:
        q = q.gt("created_at", since_ts)
    q = q.order("created_at", desc=True).limit(limit)
    res = q.execute()
    return res.data or []


def get_live_stats() -> dict[str, Any]:
    """Aggregate over the in-memory sliding window (fast, no DB dependency)."""
    now = tick_now()
    with _LOCK:
        cutoff = now - _WINDOW_SECONDS
        recent = [lat for (ts, lat) in _WINDOW if ts > cutoff]
        window = len(recent)

    avg_lat = round(sum(recent) / window, 1) if window else 0
    errors = 0
    try:
        # Fast DB count of non-2xx in the window (best-effort).
        counts = (
            db()
            .table("pc_request_logs")
            .select("status")
            .gte("created_at", (datetime.now(timezone.utc) - timedelta(seconds=_WINDOW_SECONDS)).isoformat())
            .execute()
            .data
            or []
        )
        errors = sum(1 for r in counts if r.get("status") and int(r["status"]) >= 500)
    except Exception as exc:  # noqa: BLE001
        log.debug("live_stats_db_failed", error=str(exc)[:120])

    return {
        "rps": round(window / 60.0, 2),
        "requests_last_60s": window,
        "avg_latency_ms": avg_lat,
        "error_count_60s": errors,
        "window_seconds": _WINDOW_SECONDS,
    }


def reset_window() -> None:
    with _LOCK:
        _WINDOW.clear()