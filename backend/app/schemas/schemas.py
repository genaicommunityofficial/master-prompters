from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class QrLoginRequest(BaseModel):
    """Send either a QR image (multipart) or the raw QR message text."""

    competition_id: str
    qr_message: str | None = Field(default=None, max_length=512, description="Raw QR token text, e.g. GENAI_QR_...")

    @field_validator("qr_message")
    @classmethod
    def strip_message(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            return v or None
        return v


class AuthResponse(BaseModel):
    token: str
    participant: ParticipantInfo


class ParticipantInfo(BaseModel):
    competition_id: str
    participant_id: str
    display_name: str
    email: str | None = None
    vit_registration_number: str | None = None
    already_submitted: bool = False


# ---------------------------------------------------------------------------
# Competition
# ---------------------------------------------------------------------------
class QuestionPublic(BaseModel):
    id: str
    question_number: int
    title: str
    description: str | None = None
    max_length: int
    min_length: int


class CompetitionPublic(BaseModel):
    id: str
    name: str
    slug: str
    description: str | None = None
    status: str
    start_at: str | None = None
    end_at: str | None = None
    leaderboard_visible: bool
    competition_status_open: bool = False


class CompetitionDetail(CompetitionPublic):
    questions: list[QuestionPublic]


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------
class PromptInput(BaseModel):
    question_id: str
    prompt_text: str = Field(min_length=1)


class IndividualPromptRequest(PromptInput):
    competition_id: str


class SubmissionRequest(BaseModel):
    competition_id: str
    prompts: list[PromptInput]
    idempotency_key: str | None = Field(default=None, max_length=128)


class SubmissionReceipt(BaseModel):
    submission_id: str
    status: str
    message: str


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------
class LeaderboardEntry(BaseModel):
    rank: int
    display_name: str
    total_score: float
    category_scores: dict[int, float] = {}
    average_score: float | None = None


class LeaderboardResponse(BaseModel):
    visible: bool
    entries: list[LeaderboardEntry]


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
class AdminDashboard(BaseModel):
    total_participants: int
    submitted: int
    completed: int
    failed: int
    total_prompts: int
    evaluated: int
    queued: int
    retrying: int
    evaluation_failed: int
    avg_score: float | None
    median_score: float | None
    highest_score: float | None
    lowest_score: float | None
