from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.schemas import IndividualPromptRequest, SubmissionReceipt, SubmissionRequest
from app.security.auth import get_current_participant
from app.services import competition_service as comp_svc
from app.services import submission_service as sub_svc
from app.services.submission_service import SubmissionError

router = APIRouter(prefix="/api", tags=["submissions"])


@router.post("/submissions", response_model=SubmissionReceipt)
async def submit(body: SubmissionRequest, payload: dict = Depends(get_current_participant)) -> SubmissionReceipt:
    """Submit all prompts for a competition at once (batch submission)."""
    participant_id = payload["sub"]
    competition_id = body.competition_id

    # The participant's token must match the competition they submit to.
    if payload.get("competition_id") != competition_id:
        raise HTTPException(status_code=403, detail="Competition mismatch.")

    comp = comp_svc.get_competition(competition_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Competition not found.")

    questions = comp_svc.get_questions(competition_id)

    try:
        prompts = [
            {"question_id": p.question_id, "prompt_text": p.prompt_text}
            for p in body.prompts
        ]
        validated = sub_svc.validate_submission(comp, questions, prompts)
    except SubmissionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    try:
        submission = sub_svc.create_submission(
            competition_id=competition_id,
            participant_id=participant_id,
            prompts=validated,
        )
    except SubmissionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return SubmissionReceipt(
        submission_id=submission["id"],
        status=submission.get("status") or "SUBMITTED",
        message="Your responses have been saved. Evaluation starts when an administrator runs it.",
    )


@router.post("/submissions/individual", response_model=SubmissionReceipt)
async def submit_individual(
    body: IndividualPromptRequest,
    payload: dict = Depends(get_current_participant),
) -> SubmissionReceipt:
    """Submit a single prompt individually. For individual submission flow."""
    from app.db import db as get_db

    participant_id = payload["sub"]
    competition_id = body.competition_id

    # The participant's token must match the competition they submit to.
    if payload.get("competition_id") != competition_id:
        raise HTTPException(status_code=403, detail="Competition mismatch.")

    comp = comp_svc.get_competition(competition_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Competition not found.")

    if comp.get("status") not in ("OPEN", "TEST"):
        raise HTTPException(status_code=400, detail="Competition is not currently accepting submissions.")

    # Check if already submitted
    existing = sub_svc.already_submitted(participant_id, competition_id)
    if existing and existing.get("status") in ("COMPLETED", "SUBMITTED"):
        return SubmissionReceipt(
            submission_id=existing["id"],
            status=existing["status"],
            message="Your responses have been successfully submitted.",
        )

    db = get_db()
    existing_sub = sub_svc.already_submitted(participant_id, competition_id)

    if existing_sub:
        submission = existing_sub
        sub_id = submission["id"]
    else:
        # Create a new draft submission
        result = (
            db.table("pc_submissions")
            .insert({
                "competition_id": competition_id,
                "participant_id": participant_id,
                "status": "PROCESSING",
                "submitted_at": "now()",
            })
            .execute()
            .data
        )
        if not result:
            raise HTTPException(status_code=500, detail="Could not create submission.")
        submission = result[0]
        sub_id = submission["id"]

    prompt_text = (body.prompt_text or "").strip()

    # Check if this question already has a response
    existing_response = (
        db.table("pc_responses")
        .select("id")
        .eq("submission_id", sub_id)
        .eq("question_id", body.question_id)
        .limit(1)
        .execute()
        .data
    )

    if existing_response:
        # Update existing response
        db.table("pc_responses").update({
            "prompt_text": prompt_text,
            "word_count": sub_svc._word_count(prompt_text),
            "token_estimate": sub_svc._estimate_tokens(prompt_text),
        }).eq("submission_id", sub_id).eq("question_id", body.question_id).execute()
    else:
        # Insert new response
        db.table("pc_responses").insert({
            "submission_id": sub_id,
            "question_id": body.question_id,
            "prompt_text": prompt_text,
            "word_count": sub_svc._word_count(prompt_text),
            "token_estimate": sub_svc._estimate_tokens(prompt_text),
        }).execute()

    # Check if all 5 questions have been answered
    responses = (
        db.table("pc_responses")
        .select("id")
        .eq("submission_id", sub_id)
        .execute()
        .data
        or []
    )

    if len(responses) >= 5:
        db.table("pc_submissions").update({
            "status": "SUBMITTED",
        }).eq("id", sub_id).execute()

        db.table("pc_participants").update({
            "status": "SUBMITTED",
            "submitted_at": "now()",
        }).eq("id", participant_id).execute()

        submission["status"] = "SUBMITTED"

        return SubmissionReceipt(
            submission_id=submission["id"],
            status="SUBMITTED",
            message="Your responses have been saved. Evaluation starts when an administrator runs it.",
        )

    remaining = 5 - len(responses)
    return SubmissionReceipt(
        submission_id=submission["id"],
        status="PARTIAL",
        message=f"Prompt saved. {remaining} prompt{'s' if remaining != 1 else ''} remaining.",
    )


@router.get("/submissions/exists", response_model=dict)
async def submission_exists(payload: dict = Depends(get_current_participant)) -> dict:
    participant_id = payload["sub"]
    competition_id = payload.get("competition_id")
    existing = sub_svc.already_submitted(participant_id, competition_id)
    return {"submitted": existing is not None}
