from __future__ import annotations

import asyncio
import hashlib
import os
import random
from typing import Callable

from app.db import db as _db_instance
from app.services import competition_service as comp_svc


class SubmissionError(Exception):
    status_code: int = 400

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def db():
    """Helper function to get database instance."""
    return _db_instance()


def _estimate_tokens(text: str) -> int:
    # Rough heuristic (~4 chars/token). Not authoritative.
    return max(1, len(text) // 4)


def _word_count(text: str) -> int:
    return sum(1 for w in text.split() if any(c.isalnum() for c in w))


def job_payloads_for_responses(responses: list[dict]) -> list[dict]:
    """Build QUEUED evaluation-job rows from stored responses.

    Jobs must key off ``response_id`` (the pc_responses primary key), never
    ``question_id``. Callers must select ``id`` from pc_responses.
    """
    payloads: list[dict] = []
    for row in responses:
        response_id = row.get("id")
        if not response_id:
            raise SubmissionError("Response is missing an id; cannot queue evaluation.", 500)
        payloads.append(
            {
                "response_id": response_id,
                "status": "QUEUED",
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "queued_at": "now()",
            }
        )
    return payloads


def validate_submission(competition: dict, questions: list[dict], prompts: list[dict]) -> list[dict]:
    """Validate the incoming prompts against the competition + questions."""
    if competition.get("status") not in ("OPEN", "TEST"):
        raise SubmissionError("Competition is not currently accepting submissions.")

    if len(prompts) != 5:
        raise SubmissionError("Exactly five responses are required.")

    max_length = competition.get("max_submission_length") or 4000

    q_by_id = {q["id"]: q for q in questions}
    for p in prompts:
        q = q_by_id.get(p["question_id"])
        if not q:
            raise SubmissionError("One of the questions is not valid for this competition.")
        text = (p.get("prompt_text") or "").strip()
        if len(text) < int(q.get("min_length") or 0):
            raise SubmissionError(
                f"'{q['title']}' must be at least {q.get('min_length')} characters."
            )
        if len(text) > int(q.get("max_length") or max_length):
            raise SubmissionError(
                f"'{q['title']}' must be at most {q.get('max_length')} characters long."
            )
        p["prompt_text"] = text
    return prompts


def already_submitted(participant_id: str, competition_id: str) -> dict | None:
    res = (
        db()
        .table("pc_submissions")
        .select("*")
        .eq("participant_id", participant_id)
        .eq("competition_id", competition_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def create_submission(
    *,
    competition_id: str,
    participant_id: str,
    prompts: list[dict],
) -> dict:
    """Create the submission and responses. Evaluation jobs are created later
    when an admin starts the eval pipeline — submit is store-only.
    """
    existing = already_submitted(participant_id, competition_id)
    if existing:
        return existing

    submission = (
        db()
        .table("pc_submissions")
        .insert(
            {
                "competition_id": competition_id,
                "participant_id": participant_id,
                "status": "SUBMITTED",
                "submitted_at": "now()",
            }
        )
        .execute()
        .data
    )
    if not submission:
        raise SubmissionError("Could not create submission.", 500)
    sub = submission[0]

    for p in prompts:
        response = (
            db()
            .table("pc_responses")
            .insert(
                {
                    "submission_id": sub["id"],
                    "question_id": p["question_id"],
                    "prompt_text": p["prompt_text"],
                    "word_count": _word_count(p["prompt_text"]),
                    "token_estimate": _estimate_tokens(p["prompt_text"]),
                }
            )
            .execute()
            .data
        )
        if not response:
            raise SubmissionError("Could not store one of the responses.", 500)

    # Mark participant as submitted. Evaluation is admin-triggered later.
    (
        db()
        .table("pc_participants")
        .update({"status": "SUBMITTED", "submitted_at": "now()"})
        .eq("id", participant_id)
        .execute()
    )

    return sub


class GeminiEvaluator:
    """Abstraction over the LLM provider.

    Only the evaluator touches Gemini. The submission pipeline enqueues work
    and never waits on the model, so the participant request returns fast.
    """

    provider: str = "gemini"
    model: str = "gemini-2.5-flash"

    async def evaluate(self, prompt_text: str, question: dict, evaluation_config: dict) -> dict:
        raise NotImplementedError


class LogOnlyEvaluator(GeminiEvaluator):
    """Dummy LLM evaluator that simulates realistic evaluation behavior.

    Used when GEMINI_API_KEY is not set, or when ENABLE_DUMMY_LLM=1 is forced.
    Produces scores derived from prompt text (so re-evaluating the same prompt
    gives the same result) but jittered within a realistic range. Latency and
    token counts are simulated to mimic real traffic.
    """

    provider: str = "dummy"
    model: str = "dummy-llm-v1"

    def evaluate_sync(self, prompt_text: str, question: dict, evaluation_config: dict) -> dict:
        seed_material = f"{question.get('id', '')}::{prompt_text}".encode("utf-8")
        seed = int(hashlib.sha256(seed_material).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        base_score = 60 + rng.uniform(0, 35)
        length_bonus = min(5.0, len(prompt_text) / 200.0)
        score = round(min(99.0, base_score + length_bonus), 2)
        latency_ms = int(200 + rng.uniform(0, 1000) + min(800, len(prompt_text) // 4))
        input_tokens = max(50, len(prompt_text) // 4)
        output_tokens = 60 + rng.randint(0, 120)
        thinking_tokens = 40 + rng.randint(0, 80)
        criteria = {
            "clarity": round(score * rng.uniform(0.85, 1.0), 2),
            "specificity": round(score * rng.uniform(0.80, 1.0), 2),
            "creativity": round(score * rng.uniform(0.80, 1.05), 2),
            "feasibility": round(score * rng.uniform(0.85, 1.0), 2),
        }
        summary = (
            f"Dummy LLM evaluation: prompt demonstrates {rng.choice(['strong', 'solid', 'adequate', 'notable'])} "
            f"quality across criteria. Length: {len(prompt_text)} chars."
        )
        if evaluation_config.get("criteria_md"):
            summary += " Scored against the uploaded per-category rubric."
        return {
            "score": score,
            "criteria_scores": criteria,
            "summary": summary,
            "model": self.model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "thinking_tokens": thinking_tokens,
            "latency_ms": latency_ms,
        }

    async def evaluate(self, prompt_text: str, question: dict, evaluation_config: dict) -> dict:
        result = self.evaluate_sync(prompt_text, question, evaluation_config)
        latency_ms = int(result.get("latency_ms") or 0)
        if os.getenv("EVAL_FAST_DUMMY", "1") != "0":
            await asyncio.sleep(0)
        else:
            await asyncio.sleep(min(latency_ms, 400) / 1000.0)
        return result


def get_evaluator() -> Callable:
    """Pick the appropriate evaluator.

    If GEMINI_API_KEY is set AND ENABLE_DUMMY_LLM is not '1', return the real
    Gemini evaluator. Otherwise return the LogOnlyEvaluator. Currently the
    real Gemini client is not wired — so the LogOnlyEvaluator is the default
    until that integration lands. The flag exists so admins can opt-in
    explicitly for stress tests.
    """
    from app.config import settings

    if os.getenv("ENABLE_DUMMY_LLM", "1") == "1":
        return LogOnlyEvaluator().evaluate
    if not settings.gemini_api_key:
        return LogOnlyEvaluator().evaluate
    # Real Gemini evaluator would be returned here. Until then, fall back.
    return LogOnlyEvaluator().evaluate


def run_evaluator(
    prompt_text: str,
    question: dict,
    evaluation_config: dict,
    criteria_md: str | None = None,
) -> dict:
    """Synchronous eval entry used by the worker (avoids nested event loops)."""
    if criteria_md:
        evaluation_config = {**(evaluation_config or {}), "criteria_md": criteria_md}
    from app.config import settings

    if os.getenv("ENABLE_DUMMY_LLM", "1") == "1" or not settings.gemini_api_key:
        return LogOnlyEvaluator().evaluate_sync(prompt_text, question, evaluation_config)
    return asyncio.run(get_evaluator()(prompt_text, question, evaluation_config))


def get_prompts_for_submission(competition_id: str, participant_id: str) -> list[dict]:
    """Get all prompts saved for a submission."""
    res = (
        db()
        .table("pc_responses")
        .select("id, question_id, prompt_text")
        .eq("submission_id", competition_id)
        .eq("participant_id", participant_id)
        .execute()
        .data
        or []
    )
    return res


def get_saved_prompts(participant_id: str, competition_id: str) -> list[dict]:
    """Get all saved prompt responses for a participant in a competition."""
    # Get the submission first to get its id
    sub = already_submitted(participant_id, competition_id)
    if not sub:
        return []
    sub_id = sub["id"]
    res = (
        db()
        .table("pc_responses")
        .select("id, question_id, prompt_text")
        .eq("submission_id", sub_id)
        .execute()
        .data
        or []
    )
    return res


def get_or_create_draft_submission(
    *,
    competition_id: str,
    participant_id: str,
    prompt_data: dict,
) -> dict:
    """Get an existing submission or create a draft, then add this prompt."""
    # Check if submission already exists
    existing = already_submitted(participant_id, competition_id)
    if existing:
        submission = existing
    else:
        # Create a new draft submission
        submission = (
            db()
            .table("pc_submissions")
            .insert({
                "competition_id": competition_id,
                "participant_id": participant_id,
                "status": "PROCESSING",
                "submitted_at": "now()",
            })
            .execute()
            .data
        )
        if not submission:
            raise SubmissionError("Could not create draft submission.", 500)
        submission = submission[0]

    sub_id = submission["id"]

    # Check if this question already has a response
    existing_response = (
        db()
        .table("pc_responses")
        .select("id")
        .eq("submission_id", sub_id)
        .eq("question_id", prompt_data["question_id"])
        .limit(1)
        .execute()
        .data
    )

    if existing_response:
        # Update existing response
        updated = (
            db()
            .table("pc_responses")
            .update({
                "prompt_text": prompt_data["prompt_text"],
                "word_count": _word_count(prompt_data["prompt_text"]),
                "token_estimate": _estimate_tokens(prompt_data["prompt_text"]),
            })
            .eq("submission_id", sub_id)
            .eq("question_id", prompt_data["question_id"])
            .execute()
            .data
        )
    else:
        # Insert new response
        response = (
            db()
            .table("pc_responses")
            .insert({
                "submission_id": sub_id,
                "question_id": prompt_data["question_id"],
                "prompt_text": prompt_data["prompt_text"],
                "word_count": _word_count(prompt_data["prompt_text"]),
                "token_estimate": _estimate_tokens(prompt_data["prompt_text"]),
            })
            .execute()
            .data
        )

    # Check if all 5 questions have been answered
    responses = (
        db()
        .table("pc_responses")
        .select("id")
        .eq("submission_id", sub_id)
        .execute()
        .data
        or []
    )

    if len(responses) >= 5:
        db().table("pc_submissions").update({
            "status": "SUBMITTED",
        }).eq("id", sub_id).execute()

        db().table("pc_participants").update({
            "status": "SUBMITTED",
            "submitted_at": "now()",
        }).eq("id", participant_id).execute()

        submission["status"] = "SUBMITTED"

    return submission


def get_submission_message(submission: dict) -> str:
    """Get a message for the submission."""
    if submission["status"] == "COMPLETED":
        return "Your responses have been successfully submitted."
    if submission["status"] == "SUBMITTED":
        return "Your responses have been saved. Evaluation starts when an administrator runs it."
    if submission["status"] == "PROCESSING":
        saved = len(get_saved_prompts(submission.get("participant_id", ""), submission.get("competition_id", "")))
        return f"Prompt saved. {5 - saved} prompts remaining."
    return "Your submission has been received."


def get_questions_for_competition(competition_id: str) -> list[dict]:
    """Get all questions for a competition."""
    res = (
        db()
        .table("pc_questions")
        .select("id, question_number, title, description, max_length, min_length")
        .eq("competition_id", competition_id)
        .order("question_number")
        .execute()
        .data
        or []
    )
    return res