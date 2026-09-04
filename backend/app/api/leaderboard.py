from __future__ import annotations

from fastapi import APIRouter

from app.schemas.schemas import LeaderboardEntry, LeaderboardResponse
from app.services import leaderboard_service as svc

router = APIRouter(prefix="/api", tags=["leaderboard"])


@router.get("/leaderboard/{competition_id}", response_model=LeaderboardResponse)
async def leaderboard(competition_id: str) -> LeaderboardResponse:
    data = svc.get_leaderboard(competition_id)
    return LeaderboardResponse(
        visible=data["visible"],
        entries=[LeaderboardEntry(**e) for e in data["entries"]],
    )