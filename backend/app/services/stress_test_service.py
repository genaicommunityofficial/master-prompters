from __future__ import annotations

import asyncio
import threading
import time
import uuid
from typing import Any

import httpx
import jwt

from app.config import settings
from app.db import db
from app.security.auth import ALGORITHM
from app.services import eval_run_service

TEST_COMPETITION_ID = "competition_test"
TEST_QUESTION_IDS = ("tq1", "tq2", "tq3", "tq4", "tq5")

MAX_TOTAL = 1250

_PROMPT_BODY = (
    "This is a synthetic stress-test prompt used only against the isolated TEST "
    "competition. It is long enough to satisfy the minimum length constraint."
)

_lock = threading.Lock()
_state: dict[str, Any] = {
    "status": "idle",
    "accepted": True,
    "started_at": None,
    "finished_at": None,
    "total": 0,
    "completed": 0,
    "succeeded": 0,
    "errors": 0,
    "req_per_s": 0.0,
    "avg_latency_ms": 0.0,
    "error_message": None,
    "phase": "idle",
    "jobs_enqueued": 0,
    "jobs_completed": 0,
    "jobs_failed": 0,
}


def reset_for_tests() -> None:
    with _lock:
        _state.update(
            {
                "status": "idle",
                "accepted": True,
                "started_at": None,
                "finished_at": None,
                "total": 0,
                "completed": 0,
                "succeeded": 0,
                "errors": 0,
                "req_per_s": 0.0,
                "avg_latency_ms": 0.0,
                "error_message": None,
                "phase": "idle",
                "jobs_enqueued": 0,
                "jobs_completed": 0,
                "jobs_failed": 0,
            }
        )


def clamp_params(*, total: int) -> tuple[int]:
    """Clamp the total request count. Concurrency is removed: the test fires
    requests sequentially, un-throttled, which is the realistic load a single
    Render free instance sustains when many students submit at once."""
    total = max(1, min(int(total), MAX_TOTAL))
    return (total,)


def make_prompt_payload() -> list[dict]:
    return [
        {"question_id": qid, "prompt_text": _PROMPT_BODY}
        for qid in TEST_QUESTION_IDS
    ]


def mint_token(app_settings, participant_id: str) -> str:
    now = int(time.time())
    payload = {
        "sub": participant_id,
        "competition_id": TEST_COMPETITION_ID,
        "qr_token": f"STRESS_{participant_id[:8]}",
        "role": "participant",
        "iat": now,
        "exp": now + 60 * 60 * 6,
    }
    return jwt.encode(payload, app_settings.jwt_secret, algorithm=ALGORITHM)


def summarize(rows: list[dict], elapsed_s: float) -> dict:
    succeeded = sum(1 for r in rows if r.get("ok"))
    errors = len(rows) - succeeded
    times = [float(r["ms"]) for r in rows if r.get("ok") and "ms" in r]
    elapsed_s = max(elapsed_s, 0.001)
    return {
        "total": len(rows),
        "succeeded": succeeded,
        "errors": errors,
        "req_per_s": round(len(rows) / elapsed_s, 2),
        "avg_latency_ms": round(sum(times) / len(times), 2) if times else 0.0,
    }


def ensure_test_schema(client=None) -> None:
    """Create the isolated TEST competition + questions if missing."""
    store = client or db()
    store.table("pc_competitions").upsert(
        {
            "id": TEST_COMPETITION_ID,
            "name": "TEST Competition",
            "slug": "test-competition",
            "description": "Isolated competition for load/stress testing.",
            "status": "TEST",
            "leaderboard_visible": False,
            "results_visible": False,
        }
    ).execute()
    rows = [
        {
            "id": qid,
            "competition_id": TEST_COMPETITION_ID,
            "question_number": idx,
            "title": f"Prompt {idx}",
            "description": f"Test category {idx}.",
            "input_type": "textarea",
            "max_length": 2000,
            "min_length": 20,
            "display_order": idx,
            "evaluation_config": {},
        }
        for idx, qid in enumerate(TEST_QUESTION_IDS, start=1)
    ]
    store.table("pc_questions").upsert(rows).execute()


def _set(**kwargs: Any) -> None:
    with _lock:
        _state.update(kwargs)


def get_status() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def _spawn(*, total: int, base_url: str, cleanup: bool) -> None:
    thread = threading.Thread(
        target=_run_thread,
        kwargs={
            "total": total,
            "base_url": base_url,
            "cleanup": cleanup,
        },
        daemon=True,
        name="stress-test-runner",
    )
    thread.start()


def start(*, total: int, base_url: str, cleanup: bool = False) -> dict[str, Any]:
    (total,) = clamp_params(total=total)
    with _lock:
        if _state["status"] == "running":
            snapshot = dict(_state)
            snapshot["accepted"] = False
            return snapshot
        _state.update(
            {
                "status": "running",
                "accepted": True,
                "started_at": time.time(),
                "finished_at": None,
                "total": total,
                "completed": 0,
                "succeeded": 0,
                "errors": 0,
                "req_per_s": 0.0,
                "avg_latency_ms": 0.0,
                "error_message": None,
                "phase": "seeding",
                "jobs_enqueued": 0,
                "jobs_completed": 0,
                "jobs_failed": 0,
            }
        )
        snapshot = dict(_state)
    _spawn(total=total, base_url=base_url, cleanup=cleanup)
    return snapshot


def _run_thread(*, total: int, base_url: str, cleanup: bool) -> None:
    try:
        _set(phase="seeding")
        report = asyncio.run(run(base_url, total, progress=_on_progress))
        _set(
            succeeded=report["succeeded"],
            errors=report["errors"],
            completed=report["total"],
            req_per_s=report["req_per_s"],
            avg_latency_ms=report.get("avg_latency_ms", 0.0),
            phase="evaluating",
        )
        eval_status = eval_run_service.run_pipeline(
            competition_id=TEST_COMPETITION_ID,
            batch_size=16,
            concurrency=4,
            max_retries=3,
        )
        if eval_status.get("accepted") is False:
            raise RuntimeError("An evaluation run is already in progress.")
        _set(
            phase="done",
            jobs_enqueued=eval_status.get("enqueued") or 0,
            jobs_completed=eval_status.get("completed") or 0,
            jobs_failed=eval_status.get("failed") or 0,
            status="completed",
            finished_at=time.time(),
        )
        if cleanup:
            from app.services.stress_cleanup_service import cleanup_test_data

            cleanup_test_data()
            ensure_test_schema()
    except Exception as exc:  # noqa: BLE001
        _set(status="failed", finished_at=time.time(), error_message=str(exc)[:400])


def _on_progress(completed: int, succeeded: int, errors: int) -> None:
    _set(completed=completed, succeeded=succeeded, errors=errors)


async def run(
    base: str,
    total: int,
    progress=None,
) -> dict:
    """Fire `total` submissions sequentially, un-throttled, against the TEST
    competition. A single Render free instance serves requests serially, so this
    is the realistic simulation of 300 students submitting at once: every
    request is issued back-to-back and the server drains them in arrival order.
    """
    (total,) = clamp_params(total=total)
    ensure_test_schema()
    store = db()
    participants = _insert_participants(store, total)
    prompts = make_prompt_payload()
    start_all = time.time()
    base = base.rstrip("/")

    async with httpx.AsyncClient(timeout=60.0) as client:
        succeeded = 0
        errors = 0
        latencies: list[float] = []
        status_codes: dict[int, int] = {}

        for i, pid in enumerate(participants):
            token = mint_token(settings, pid)
            t0 = time.time()
            try:
                resp = await client.post(
                    f"{base}/api/submissions",
                    json={"competition_id": TEST_COMPETITION_ID, "prompts": prompts},
                    headers={"Authorization": f"Bearer {token}"},
                )
                ok = resp.status_code in (200, 409)
                status_codes[resp.status_code] = status_codes.get(resp.status_code, 0) + 1
            except Exception:  # noqa: BLE001
                ok = False
                status_codes[0] = status_codes.get(0, 0) + 1
            ms = (time.time() - t0) * 1000
            latencies.append(ms)
            if ok:
                succeeded += 1
            else:
                errors += 1
            if progress and (i % max(1, total // 20) == 0 or i == total - 1):
                progress(i + 1, succeeded, errors)

    elapsed = time.time() - start_all
    return {
        "total": total,
        "succeeded": succeeded,
        "errors": errors,
        "req_per_s": round(total / max(elapsed, 0.001), 2),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        "max_latency_ms": round(max(latencies), 2) if latencies else 0.0,
        "p95_latency_ms": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 2)
        if latencies else 0.0,
        "status_codes": status_codes,
    }


def _insert_participants(store, total: int) -> list[str]:
    ids: list[str] = []
    batch: list[dict] = []
    for _ in range(total):
        pid = str(uuid.uuid4())
        ids.append(pid)
        batch.append(
            {
                "id": pid,
                "competition_id": TEST_COMPETITION_ID,
                "registration_id": str(uuid.uuid4()),
                "qr_token": f"STRESS_{pid.replace('-', '')[:16]}",
                "display_name": f"Stress {pid[:8]}",
                "email": f"stress-{pid[:8]}@test.local",
                "status": "REGISTERED",
            }
        )
        if len(batch) >= 50:
            store.table("pc_participants").insert(batch).execute()
            batch = []
    if batch:
        store.table("pc_participants").insert(batch).execute()
    return ids
