"""Background queue worker that continuously processes evaluation jobs.

Runs as an asyncio task spawned on app startup. Polls the database for QUEUED
evaluation jobs, processes them in batches, and sleeps briefly when the queue
is empty. Survives transient DB failures with exponential backoff.
"""

from __future__ import annotations

import asyncio
import contextlib

from app.services import evaluation_service
from app.utils.logging_utils import log

# Worker configuration
BATCH_SIZE = 5
POLL_INTERVAL_S = 1.5  # When queue is empty
ACTIVE_POLL_INTERVAL_S = 0.2  # When queue is non-empty
MAX_ERRORS_BEFORE_BACKOFF = 5
BACKOFF_SLEEP_S = 5.0

# Module-level task handle so the worker can be shut down on app exit.
_worker_task: asyncio.Task | None = None
_should_stop = False


async def _worker_loop() -> None:
    """Continuously drain the evaluation queue."""
    consecutive_errors = 0
    log.info("queue_worker_started", batch_size=BATCH_SIZE)

    while not _should_stop:
        try:
            processed = await asyncio.to_thread(
                evaluation_service.process_queued_batch, BATCH_SIZE
            )
            if processed > 0:
                log.info("queue_worker_processed", count=processed)
                await asyncio.sleep(ACTIVE_POLL_INTERVAL_S)
            else:
                await asyncio.sleep(POLL_INTERVAL_S)
            consecutive_errors = 0
        except Exception as exc:  # noqa: BLE001
            consecutive_errors += 1
            log.warning(
                "queue_worker_error",
                error=str(exc),
                consecutive_errors=consecutive_errors,
            )
            if consecutive_errors >= MAX_ERRORS_BEFORE_BACKOFF:
                log.error("queue_worker_backing_off", sleep_s=BACKOFF_SLEEP_S)
                await asyncio.sleep(BACKOFF_SLEEP_S)
                consecutive_errors = 0
            else:
                await asyncio.sleep(1.0)

    log.info("queue_worker_stopped")


def start() -> None:
    """No-op: evaluation is started by an administrator, not on API boot."""
    log.info("queue_worker_auto_drain_disabled")


async def stop() -> None:
    """Signal the worker to stop and wait for it to exit."""
    global _worker_task, _should_stop
    _should_stop = True
    if _worker_task is not None:
        _worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await _worker_task
        _worker_task = None
