from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, Request, Response, UploadFile, status
from pydantic import BaseModel

from app.security.auth import get_current_admin
from app.services import admin_analytics_service, admin_auth_service, admin_registration_service, admin_service, competition_service
from app.services import eval_criteria_service
from app.services import eval_run_service
from app.services import leaderboard_service as lb_svc
from app.services import request_log_service
from app.services.submission_service import EvalConfigError

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
def dashboard(
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> DashboardResponse:
    cid = _scoped_competition(payload, competition_id)
    return DashboardResponse(metrics=admin_service.get_dashboard(cid))


@router.get("/submissions")
def admin_submissions(
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> list[dict]:
    return admin_service.get_admin_submissions(_scoped_competition(payload, competition_id))


@router.get("/evaluations")
def admin_evaluations(
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> list[dict]:
    return admin_service.get_admin_evaluations(_scoped_competition(payload, competition_id))


LIVE_COMPETITION_FALLBACK = "competition_2026"
TEST_COMPETITION_ID = "competition_test"


class EvalStartRequest(BaseModel):
    competition_id: str | None = None
    batch_size: int = 16
    concurrency: int = 8
    max_retries: int = 3
    mode: Literal["restart", "resume", "retry_failed"] = "restart"


def _allowed_eval_competitions(payload: dict) -> set[str]:
    live = payload.get("competition_id") or LIVE_COMPETITION_FALLBACK
    return {live, TEST_COMPETITION_ID}


def _scoped_competition(payload: dict, requested: str | None) -> str:
    live = payload.get("competition_id") or LIVE_COMPETITION_FALLBACK
    competition_id = requested or live
    if competition_id not in _allowed_eval_competitions(payload):
        raise HTTPException(status_code=403, detail="Competition is not allowed for this admin.")
    return competition_id


@router.post("/evaluations/start")
def start_evaluation(
    body: EvalStartRequest,
    payload: dict = Depends(require_admin),
) -> dict:
    competition_id = _scoped_competition(payload, body.competition_id)
    try:
        return eval_run_service.start(
            competition_id=competition_id,
            batch_size=body.batch_size,
            concurrency=body.concurrency,
            max_retries=body.max_retries,
            mode=body.mode,
        )
    except EvalConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/evaluations/pause")
def pause_evaluation(payload: dict = Depends(require_admin)) -> dict:
    return eval_run_service.pause()


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
def analytics(
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> AnalyticsResponse:
    cid = _scoped_competition(payload, competition_id)
    return AnalyticsResponse(
        analytics=admin_analytics_service.get_analytics(cid),
    )


class ExportResponse(BaseModel):
    filename: str
    row_count: int
    columns: list[str]


@router.get("/export", response_model=ExportResponse)
def export_prompts(
    category: Annotated[int, Query(ge=1, le=5)] | None = None,
    format: str = "csv",
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> ExportResponse:
    cid = _scoped_competition(payload, competition_id)
    data, columns, filename = admin_analytics_service.build_export(
        cid,
        category=category,
    )
    # CSV is returned by the dedicated CSV route below; this route reports shape.
    return ExportResponse(filename=filename, row_count=len(data), columns=[c[1] for c in columns])


@router.get("/export/csv")
def export_prompts_csv(
    category: Annotated[int, Query(ge=1, le=5)] | None = None,
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
):
    from fastapi.responses import Response

    cid = _scoped_competition(payload, competition_id)
    csv_bytes, columns, filename = admin_analytics_service.build_export_csv(
        cid,
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
    content_md: str = ""
    locked: bool = False
    updated_at: str | None = None


class CriteriaSaveRequest(BaseModel):
    content_md: str


@router.get("/criteria", response_model=list[CriteriaListEntry])
def list_criteria(
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> list[dict]:
    """List the uploaded per-category markdown rubrics for this competition."""
    cid = _scoped_competition(payload, competition_id)
    rows = eval_criteria_service.get_criteria_for_competition(cid)
    out = []
    for qn in sorted(rows):
        r = rows[qn]
        out.append(
            {
                "question_number": qn,
                "file_name": r.get("file_name", ""),
                "content_hash": r.get("content_hash", ""),
                "content_md": r.get("content_md") or "",
                "locked": bool(r.get("locked")),
                "updated_at": r.get("updated_at"),
            }
        )
    return out


@router.get("/criteria/{category}")
def get_criteria(
    category: Annotated[int, Path(ge=1, le=5)],
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> dict:
    cid = _scoped_competition(payload, competition_id)
    rows = eval_criteria_service.get_criteria_for_competition(cid)
    r = rows.get(category)
    if not r:
        return {
            "question_number": category,
            "file_name": None,
            "content_md": "",
            "locked": False,
        }
    return {
        "question_number": category,
        "file_name": r.get("file_name"),
        "content_md": r.get("content_md") or "",
        "locked": bool(r.get("locked")),
    }


def _save_criteria(cid: str, category: int, content: str, file_name: str) -> CriteriaUploadResponse:
    try:
        saved = eval_criteria_service.upsert_criteria(
            competition_id=cid,
            question_number=category,
            file_name=file_name,
            content_md=content,
        )
    except eval_criteria_service.CriteriaLockedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except eval_criteria_service.CriteriaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CriteriaUploadResponse(
        question_number=category,
        file_name=saved["file_name"],
        content_hash=saved["content_hash"],
    )


@router.post("/criteria", response_model=CriteriaUploadResponse)
async def upload_criteria(
    category: Annotated[int, Query(ge=1, le=5)],
    file: UploadFile,
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> CriteriaUploadResponse:
    """Upload/replace the markdown rubric for a single category."""
    cid = _scoped_competition(payload, competition_id)
    content = (await file.read()).decode("utf-8", errors="replace")
    if not content.strip():
        raise HTTPException(status_code=400, detail="Criteria file is empty.")
    return _save_criteria(cid, category, content, file.filename or "criteria.md")


@router.put("/criteria/{category}", response_model=CriteriaUploadResponse)
def save_criteria_text(
    category: Annotated[int, Path(ge=1, le=5)],
    body: CriteriaSaveRequest,
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> CriteriaUploadResponse:
    """Save pasted markdown for a category."""
    cid = _scoped_competition(payload, competition_id)
    return _save_criteria(cid, category, body.content_md, "criteria.md")


class CriteriaLockResponse(BaseModel):
    question_number: int
    locked: bool


@router.post("/criteria/{category}/lock", response_model=CriteriaLockResponse)
def lock_criteria(
    category: Annotated[int, Path(ge=1, le=5)],
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> CriteriaLockResponse:
    cid = _scoped_competition(payload, competition_id)
    try:
        saved = eval_criteria_service.set_criteria_locked(cid, category, True)
    except eval_criteria_service.CriteriaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CriteriaLockResponse(question_number=category, locked=bool(saved["locked"]))


@router.post("/criteria/{category}/unlock", response_model=CriteriaLockResponse)
def unlock_criteria(
    category: Annotated[int, Path(ge=1, le=5)],
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> CriteriaLockResponse:
    cid = _scoped_competition(payload, competition_id)
    try:
        saved = eval_criteria_service.set_criteria_locked(cid, category, False)
    except eval_criteria_service.CriteriaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CriteriaLockResponse(question_number=category, locked=bool(saved["locked"]))


@router.post("/criteria/copy-live")
def copy_live_criteria(
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> dict:
    """Copy live-competition rubrics onto the currently scoped competition (test)."""
    dest = _scoped_competition(payload, competition_id)
    live = payload.get("competition_id") or LIVE_COMPETITION_FALLBACK
    if dest == live:
        raise HTTPException(status_code=400, detail="Switch to Test mode to copy live rubrics.")
    written = eval_criteria_service.copy_criteria(live, dest)
    return {"success": True, "copied": written, "source": live, "destination": dest}


@router.get("/eval-status")
def eval_status(
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> dict:
    """Optimized evaluation-pipeline state for an admin-scoped competition."""
    from app.services.eval_status_service import get_eval_progress

    return get_eval_progress(_scoped_competition(payload, competition_id))


@router.get("/leaderboard")
def admin_leaderboard(
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> dict:
    """Admin view of a competition leaderboard, even before it is published."""
    return lb_svc.get_leaderboard(_scoped_competition(payload, competition_id), ignore_visibility=True)


@router.get("/participation")
def participation_funnel(
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> dict:
    """Registered -> logged in -> submitted funnel for an admin-scoped competition."""
    from app.services.eval_status_service import FunnelMigrationError, get_participation_funnel

    try:
        return get_participation_funnel(_scoped_competition(payload, competition_id))
    except FunnelMigrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class LeaderboardPublishResponse(BaseModel):
    success: bool
    visible: bool


class RegistrationCreateRequest(BaseModel):
    registration_number: str
    display_name: str | None = None
    email: str | None = None


@router.get("/participants")
def list_participants(
    response: Response,
    competition_id: str | None = Query(default=None),
    _cache_bust: int | None = Query(default=None, alias="t", include_in_schema=False),
    payload: dict = Depends(require_admin),
) -> dict:
    """Event registrations (read-only) merged with admin-added pc_participants."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    cid = _scoped_competition(payload, competition_id)
    try:
        return admin_registration_service.list_roster(cid)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not load participants: {exc}") from exc


@router.get("/registrations")
def list_registrations(
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> list[dict]:
    """Admin-added extras only (never writes to registrations)."""
    cid = _scoped_competition(payload, competition_id)
    try:
        return admin_registration_service.list_registrations(cid)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not load registrations: {exc}") from exc


@router.post("/registrations")
def create_registration(
    body: RegistrationCreateRequest,
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> dict:
    """Manually register a participant into pc_participants, not registrations."""
    cid = _scoped_competition(payload, competition_id)
    try:
        row = admin_registration_service.register_participant(
            competition_id=cid,
            registration_number=body.registration_number,
            display_name=body.display_name,
            email=body.email,
        )
    except admin_registration_service.RegistrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Could not register participant: {exc}") from exc
    return {
        "success": True,
        "id": row["id"],
        "registration_number": row.get("registration_number"),
        "display_name": row.get("display_name"),
    }


class ParticipantDropRequest(BaseModel):
    id: str


@router.post("/participants/drop")
def drop_participant(
    body: ParticipantDropRequest,
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> dict:
    """Drop a participant from this competition. Never writes to registrations."""
    cid = _scoped_competition(payload, competition_id)
    try:
        return admin_registration_service.drop_participant(cid, body.id)
    except admin_registration_service.RegistrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Could not drop participant: {exc}") from exc


@router.post("/competition/open")
def open_competition(
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> dict:
    cid = _scoped_competition(payload, competition_id)
    comp = competition_service.set_status(cid, "OPEN")
    return {"success": True, "status": comp.get("status") if comp else None}


@router.post("/competition/close")
def close_competition(
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> dict:
    cid = _scoped_competition(payload, competition_id)
    # TEST competitions use status TEST when not open; closing live uses CLOSED.
    next_status = "TEST" if cid == TEST_COMPETITION_ID else "CLOSED"
    comp = competition_service.set_status(cid, next_status)
    return {"success": True, "status": comp.get("status") if comp else None}


@router.post("/leaderboard/publish", response_model=LeaderboardPublishResponse)
def publish_leaderboard(
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> LeaderboardPublishResponse:
    cid = _scoped_competition(payload, competition_id)
    lb_svc.set_leaderboard_visible(cid, True)
    return LeaderboardPublishResponse(success=True, visible=True)


@router.post("/leaderboard/unpublish", response_model=LeaderboardPublishResponse)
def unpublish_leaderboard(
    competition_id: str | None = Query(default=None),
    payload: dict = Depends(require_admin),
) -> LeaderboardPublishResponse:
    cid = _scoped_competition(payload, competition_id)
    lb_svc.set_leaderboard_visible(cid, False)
    return LeaderboardPublishResponse(success=True, visible=False)