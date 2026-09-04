from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, UploadFile, status
from pydantic import BaseModel

from app.security.auth import get_current_admin
from app.services import admin_analytics_service, admin_auth_service, admin_service, competition_service
from app.services import eval_criteria_service
from app.services import eval_run_service
from app.services import leaderboard_service as lb_svc
from app.services import request_log_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminLoginResponse(BaseModel):
    token: str
    username: str
    role: str


def require_admin(payload: dict = Depends(get_current_admin)) -> dict:
    return payload


@router.post("/login", response_model=AdminLoginResponse)
def admin_login(body: AdminLoginRequest, request: Request) -> AdminLoginResponse:
    ip = request.client.host if request.client else ""
    try:
        result = admin_auth_service.login_admin(body.username, body.password, ip)
    except admin_auth_service.RateLimitedError:
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
    if not result:
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    return AdminLoginResponse(**result)


class DashboardResponse(BaseModel):
    metrics: dict


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(payload: dict = Depends(require_admin)) -> DashboardResponse:
    competition_id = payload["competition_id"]
    return DashboardResponse(metrics=admin_service.get_dashboard(competition_id))


@router.get("/submissions")
def admin_submissions(payload: dict = Depends(require_admin)) -> list[dict]:
    competition_id = payload["competition_id"]
    return admin_service.get_admin_submissions(competition_id)


@router.get("/evaluations")
def admin_evaluations(payload: dict = Depends(require_admin)) -> list[dict]:
    competition_id = payload["competition_id"]
    return admin_service.get_admin_evaluations(competition_id)


LIVE_COMPETITION_FALLBACK = "competition_2026"
TEST_COMPETITION_ID = "competition_test"


class EvalStartRequest(BaseModel):
    competition_id: str | None = None
    batch_size: int = 8
    concurrency: int = 4
    max_retries: int = 3
    llm_mode: str | None = None


def _allowed_eval_competitions(payload: dict) -> set[str]:
    live = payload.get("competition_id") or LIVE_COMPETITION_FALLBACK
    return {live, TEST_COMPETITION_ID}


@router.post("/evaluations/start")
def start_evaluation(
    body: EvalStartRequest,
    payload: dict = Depends(require_admin),
) -> dict:
    live = payload.get("competition_id") or LIVE_COMPETITION_FALLBACK
    competition_id = body.competition_id or live
    if competition_id not in _allowed_eval_competitions(payload):
        raise HTTPException(status_code=403, detail="Competition is not allowed for this admin.")
    return eval_run_service.start(
        competition_id=competition_id,
        batch_size=body.batch_size,
        concurrency=body.concurrency,
        max_retries=body.max_retries,
        llm_mode=body.llm_mode,
    )


@router.get("/evaluations/run")
def evaluation_run(payload: dict = Depends(require_admin)) -> dict:
    return eval_run_service.get_status()


@router.get("/evaluations/logs")
def evaluation_logs(
    since: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    payload: dict = Depends(require_admin),
) -> dict:
    return eval_run_service.get_logs(since=since, limit=limit)


class LiveStatsResponse(BaseModel):
    rps: float
    requests_last_60s: int
    avg_latency_ms: float
    error_count_60s: int
    window_seconds: int


class LiveLogsResponse(BaseModel):
    logs: list[dict]
    stats: dict


@router.get("/monitor/live", response_model=LiveStatsResponse)
def live_stats(payload: dict = Depends(require_admin)) -> LiveStatsResponse:
    return LiveStatsResponse(**request_log_service.get_live_stats())


@router.get("/monitor/logs", response_model=LiveLogsResponse)
def live_logs(
    since_ts: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 300,
    payload: dict = Depends(require_admin),
) -> LiveLogsResponse:
    logs = request_log_service.get_recent_logs(since_ts, limit=limit)
    return LiveLogsResponse(
        logs=logs,
        stats=request_log_service.get_live_stats(),
    )


class AnalyticsResponse(BaseModel):
    analytics: dict


@router.get("/analytics", response_model=AnalyticsResponse)
def analytics(payload: dict = Depends(require_admin)) -> AnalyticsResponse:
    competition_id = payload["competition_id"]
    return AnalyticsResponse(
        analytics=admin_analytics_service.get_analytics(competition_id),
    )


class ExportResponse(BaseModel):
    filename: str
    row_count: int
    columns: list[str]


@router.get("/export", response_model=ExportResponse)
def export_prompts(
    category: Annotated[int, Query(ge=1, le=5)] | None = None,
    format: str = "csv",
    payload: dict = Depends(require_admin),
) -> ExportResponse:
    competition_id = payload["competition_id"]
    data, columns, filename = admin_analytics_service.build_export(
        competition_id,
        category=category,
    )
    # CSV is returned by the dedicated CSV route below; this route reports shape.
    return ExportResponse(filename=filename, row_count=len(data), columns=[c[0] for c in columns])


@router.get("/export/csv")
def export_prompts_csv(
    category: Annotated[int, Query(ge=1, le=5)] | None = None,
    payload: dict = Depends(require_admin),
):
    from fastapi.responses import Response

    competition_id = payload["competition_id"]
    csv_bytes, columns, filename = admin_analytics_service.build_export_csv(
        competition_id,
        category=category,
    )
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class CriteriaUploadResponse(BaseModel):
    question_number: int
    file_name: str
    content_hash: str
    updated_at: str | None = None


class CriteriaListEntry(BaseModel):
    question_number: int
    file_name: str
    content_hash: str
    updated_at: str | None = None


@router.get("/criteria", response_model=list[CriteriaListEntry])
def list_criteria(payload: dict = Depends(require_admin)) -> list[dict]:
    """List the uploaded per-category markdown rubrics for this competition."""
    competition_id = payload["competition_id"]
    rows = eval_criteria_service.get_criteria_for_competition(competition_id)
    out = []
    for qn in sorted(rows):
        r = rows[qn]
        out.append(
            {
                "question_number": qn,
                "file_name": r.get("file_name", ""),
                "content_hash": r.get("content_hash", ""),
                "updated_at": r.get("updated_at"),
            }
        )
    return out


@router.get("/criteria/{category}")
def get_criteria(
    category: Annotated[int, Path(ge=1, le=5)],
    payload: dict = Depends(require_admin),
) -> dict:
    competition_id = payload["competition_id"]
    rows = eval_criteria_service.get_criteria_for_competition(competition_id)
    r = rows.get(category)
    if not r:
        return {"question_number": category, "file_name": None, "content_md": ""}
    return {
        "question_number": category,
        "file_name": r.get("file_name"),
        "content_md": r.get("content_md"),
    }


@router.post("/criteria", response_model=CriteriaUploadResponse)
async def upload_criteria(
    category: Annotated[int, Query(ge=1, le=5)],
    file: UploadFile,
    payload: dict = Depends(require_admin),
) -> CriteriaUploadResponse:
    """Upload/replace the markdown rubric for a single category."""
    competition_id = payload["competition_id"]
    content = (await file.read()).decode("utf-8", errors="replace")
    if not content.strip():
        raise HTTPException(status_code=400, detail="Criteria file is empty.")
    name = file.filename or "criteria.md"
    saved = eval_criteria_service.upsert_criteria(
        competition_id=competition_id,
        question_number=category,
        file_name=name,
        content_md=content,
    )
    return CriteriaUploadResponse(
        question_number=category,
        file_name=saved["file_name"],
        content_hash=saved["content_hash"],
    )


class LlmModeRequest(BaseModel):
    mode: str  # "dummy" or "gemini"


@router.post("/test/llm-mode")
def set_llm_mode(body: LlmModeRequest, payload: dict = Depends(require_admin)) -> dict:
    """Set the LLM mode used by the evaluator for the next run."""
    if body.mode not in ("dummy", "gemini"):
        raise HTTPException(status_code=400, detail="Mode must be 'dummy' or 'gemini'")
    os.environ["ENABLE_DUMMY_LLM"] = "0" if body.mode == "gemini" else "1"
    return {"mode": body.mode, "message": f"LLM mode set to {body.mode}"}


@router.get("/test/llm-mode")
def get_llm_mode(payload: dict = Depends(require_admin)) -> dict:
    mode = "gemini" if os.getenv("ENABLE_DUMMY_LLM", "1") == "0" else "dummy"
    return {"mode": mode}


class SeedRequest(BaseModel):
    participant_count: int = 50


@router.post("/test/seed")
def seed_test_data(body: SeedRequest, payload: dict = Depends(require_admin)) -> dict:
    """Seed the TEST competition with realistic test data."""
    from app.services import test_seeding_service

    if body.participant_count < 1 or body.participant_count > 1000:
        raise HTTPException(status_code=400, detail="Participant count must be 1-1000")
    result = test_seeding_service.seed_test_data(body.participant_count)
    return {"success": True, **result}


@router.post("/test/cleanup")
def cleanup_test_data(payload: dict = Depends(require_admin)) -> dict:
    """Clean up all TEST competition data."""
    from app.services import test_seeding_service

    result = test_seeding_service.cleanup_test_data()
    return {"success": True, **result}


@router.get("/test/status")
def test_status(payload: dict = Depends(require_admin)) -> dict:
    """Get current TEST competition stats."""
    from app.db import db

    store = db()
    subs = (
        store.table("pc_submissions")
        .select("id")
        .eq("competition_id", "competition_test")
        .execute()
        .data
        or []
    )
    sub_ids = [s["id"] for s in subs]
    responses = 0
    evaluated = 0
    if sub_ids:
        # Response ids in chunks of 100
        resp_by_sub: list[str] = []
        for i in range(0, len(sub_ids), 100):
            chunk = sub_ids[i : i + 100]
            resp_rows = (
                store.table("pc_responses")
                .select("id")
                .in_("submission_id", chunk)
                .execute()
                .data
                or []
            )
            resp_by_sub.extend(r["id"] for r in resp_rows)
        responses = len(resp_by_sub)
        if resp_by_sub:
            evaluated = 0
            for i in range(0, len(resp_by_sub), 100):
                chunk = resp_by_sub[i : i + 100]
                ev_rows = (
                    store.table("pc_evaluations")
                    .select("id")
                    .in_("response_id", chunk)
                    .execute()
                    .data
                    or []
                )
                evaluated += len(ev_rows)
    return {
        "participants": len(sub_ids),
        "submissions": len(sub_ids),
        "responses": responses,
        "evaluated": evaluated,
        "pending": responses - evaluated,
    }


class LeaderboardPublishResponse(BaseModel):
    success: bool
    visible: bool


@router.post("/competition/open")
def open_competition(payload: dict = Depends(require_admin)) -> dict:
    competition_id = payload["competition_id"]
    comp = competition_service.set_status(competition_id, "OPEN")
    return {"success": True, "status": comp.get("status") if comp else None}


@router.post("/competition/close")
def close_competition(payload: dict = Depends(require_admin)) -> dict:
    competition_id = payload["competition_id"]
    comp = competition_service.set_status(competition_id, "CLOSED")
    return {"success": True, "status": comp.get("status") if comp else None}


@router.post("/leaderboard/publish", response_model=LeaderboardPublishResponse)
def publish_leaderboard(payload: dict = Depends(require_admin)) -> LeaderboardPublishResponse:
    competition_id = payload["competition_id"]
    lb_svc.set_leaderboard_visible(competition_id, True)
    return LeaderboardPublishResponse(success=True, visible=True)


@router.post("/leaderboard/unpublish", response_model=LeaderboardPublishResponse)
def unpublish_leaderboard(payload: dict = Depends(require_admin)) -> LeaderboardPublishResponse:
    competition_id = payload["competition_id"]
    lb_svc.set_leaderboard_visible(competition_id, False)
    return LeaderboardPublishResponse(success=True, visible=False)