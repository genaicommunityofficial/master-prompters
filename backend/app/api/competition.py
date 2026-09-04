from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.schemas import CompetitionDetail, CompetitionPublic
from app.services import competition_service as svc

router = APIRouter(prefix="/api/competitions", tags=["competition"])


@router.get("/active", response_model=CompetitionPublic)
async def get_active_competition() -> CompetitionPublic:
    """Return the first OPEN competition, used to drive the participant flow."""
    res = svc.get_competition_by_slug("master-prompters-2-0") or svc.get_competition_by_slug("default")
    if not res:
        raise HTTPException(status_code=404, detail="No active competition.")
    return CompetitionPublic(**svc.to_public_competition(res))


@router.get("/{competition_id}", response_model=CompetitionDetail)
async def get_competition(competition_id: str) -> CompetitionDetail:
    comp = svc.get_competition(competition_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Competition not found.")
    questions = [svc.to_public_question(q) for q in svc.get_questions(competition_id)]
    base = svc.to_public_competition(comp)
    return CompetitionDetail(**base, questions=questions)