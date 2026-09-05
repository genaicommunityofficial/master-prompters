from __future__ import annotations

import json
import time

from app.db import db as _db_instance
from app.services import competition_service as comp_svc
from app.services.eval_cost import estimate_cost_usd

BATCH_SIZE = 10


class SubmissionError(Exception):
    status_code: int = 400

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class EvalConfigError(Exception):
    """Raised when the LLM cannot be used, e.g. missing API key."""

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
                "model": gemini_model_name(),
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

    If a draft (PROCESSING) submission already exists for this participant —
    e.g. created by the individual-submit flow — the prompts are upserted into
    it instead of being silently dropped.
    """
    existing = already_submitted(participant_id, competition_id)
    if existing and existing.get("status") in ("SUBMITTED", "COMPLETED"):
        return existing

    if existing:
        sub = existing
        for p in prompts:
            _upsert_response(sub["id"], p)
        return _refresh_submission_state(sub, participant_id)

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
        _upsert_response(sub["id"], p)

    # Mark participant as submitted. Evaluation is admin-triggered later.
    (
        db()
        .table("pc_participants")
        .update({"status": "SUBMITTED", "submitted_at": "now()"})
        .eq("id", participant_id)
        .execute()
    )

    return sub


def _upsert_response(sub_id: str, prompt: dict) -> None:
    """Insert or update one response row for a submission."""
    existing_response = (
        db()
        .table("pc_responses")
        .select("id")
        .eq("submission_id", sub_id)
        .eq("question_id", prompt["question_id"])
        .limit(1)
        .execute()
        .data
        or []
    )
    payload = {
        "prompt_text": prompt["prompt_text"],
        "word_count": _word_count(prompt["prompt_text"]),
        "token_estimate": _estimate_tokens(prompt["prompt_text"]),
    }
    if existing_response:
        (
            db()
            .table("pc_responses")
            .update(payload)
            .eq("id", existing_response[0]["id"])
            .execute()
        )
    else:
        (
            db()
            .table("pc_responses")
            .insert({"submission_id": sub_id, "question_id": prompt["question_id"], **payload})
            .execute()
        )


def _refresh_submission_state(sub: dict, participant_id: str) -> dict:
    """Finalize a draft submission once all 5 responses are present."""
    sub_id = sub["id"]
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
        (
            db()
            .table("pc_submissions")
            .update({"status": "SUBMITTED", "submitted_at": "now()"})
            .eq("id", sub_id)
            .execute()
        )
        (
            db()
            .table("pc_participants")
            .update({"status": "SUBMITTED", "submitted_at": "now()"})
            .eq("id", participant_id)
            .execute()
        )
        sub["status"] = "SUBMITTED"
    return sub


def gemini_model_name() -> str:
    """Model id sent to the Gemini API. Override with GEMINI_MODEL."""
    from app.config import settings

    name = str(getattr(settings, "gemini_model", "") or "").strip()
    return name or "gemini-3.6-flash"


def ensure_gemini_configured() -> None:
    """Raises EvalConfigError unless a real Gemini API key is configured."""
    from app.config import settings

    if not settings.gemini_api_key:
        raise EvalConfigError(
            "Gemini API key is not configured on the server. "
            "Set GEMINI_API_KEY before starting an evaluation run."
        )


def run_evaluator(
    prompt_text: str,
    question: dict,
    evaluation_config: dict,
    criteria_md: str | None = None,
) -> dict:
    """Synchronous single prompt evaluation via the real Gemini LLM."""
    results = run_batch_evaluator(
        items=[{"prompt_text": prompt_text}],
        question=question,
        evaluation_config=evaluation_config,
        criteria_md=criteria_md,
        concurrency=1,
    )
    return results[0]


def run_batch_evaluator(
    items: list[dict],
    question: dict,
    evaluation_config: dict,
    criteria_md: str | None = None,
    concurrency: int = 8,
) -> list[dict]:
    """Score each prompt independently, with parallel Gemini HTTP calls.

    Sharing one request across many prompts mixed scores and failed JSON parses.
    One prompt per call keeps rubric judgments independent; concurrency cuts
    wall-clock time. Database writes stay on the caller thread.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    ensure_gemini_configured()
    if criteria_md:
        evaluation_config = {**(evaluation_config or {}), "criteria_md": criteria_md}
    if not items:
        return []
    workers = max(1, min(int(concurrency), len(items)))
    if workers == 1 or len(items) == 1:
        return [_gemini_evaluate_one(item, question, evaluation_config) for item in items]

    results: list[dict | None] = [None] * len(items)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="gemini-eval") as pool:
        futures = {
            pool.submit(_gemini_evaluate_one, item, question, evaluation_config): i
            for i, item in enumerate(items)
        }
        for fut in as_completed(futures):
            results[futures[fut]] = fut.result()
    missing = [i for i, row in enumerate(results) if row is None]
    if missing:
        raise RuntimeError(f"Gemini returned no result for prompts {missing}")
    return results  # type: ignore[return-value]


def _is_retryable_gemini_error(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    tokens = (
        "429",
        "resource exhausted",
        "resourceexhausted",
        "unavailable",
        "503",
        "500",
        "deadline",
        "internal",
        "too many requests",
        "overloaded",
    )
    return name in {
        "resourceexhausted",
        "serviceunavailable",
        "internalservererror",
        "toomanyrequests",
        "deadlineexceeded",
    } or any(tok in msg for tok in tokens)


def _gemini_evaluate_one(
    item: dict,
    question: dict,
    evaluation_config: dict,
) -> dict:
    """One competition prompt → one Gemini JSON score. Retries transient API errors."""
    import google.generativeai as genai
    from app.config import settings

    genai.configure(api_key=settings.gemini_api_key)
    model_name = gemini_model_name()
    model = genai.GenerativeModel(
        model_name,
        generation_config={
            "temperature": 0,
            "response_mime_type": "application/json",
        },
    )

    criteria_md = evaluation_config.get("criteria_md", "")
    question_text = question.get("description") or question.get("title") or ""
    prompt_text = item["prompt_text"]

    user_content = (
        "You are an expert prompt engineer evaluating one competition prompt.\n\n"
        f"## Question / Task\n{question_text}\n\n"
    )
    if criteria_md:
        user_content += f"## Evaluation Criteria (Rubric)\n{criteria_md}\n\n"
    user_content += (
        f"## Prompt to Evaluate\n{prompt_text}\n\n"
        "## Instructions\n"
        "Score this prompt independently against the criteria. Do not compare it to other prompts.\n"
        "Return a JSON object with exactly these keys:\n"
        '  - "score": number 0-100 (overall score)\n'
        '  - "criteria_scores": object with keys matching the rubric dimensions '
        "(e.g. clarity, specificity, creativity, feasibility) — each a number 0-100\n"
        '  - "summary": string (one sentence explaining the score)\n'
        "Return ONLY the JSON object.\n"
    )

    last_exc: Exception | None = None
    raw = ""
    latency_ms = 0
    response = None
    for attempt in range(4):
        t0 = time.monotonic()
        try:
            response = model.generate_content(user_content)
            latency_ms = int((time.monotonic() - t0) * 1000)
            raw = (response.text or "").strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                if len(parsed) != 1 or not isinstance(parsed[0], dict):
                    raise ValueError("Gemini returned a JSON array instead of one score object")
                parsed = parsed[0]
            if not isinstance(parsed, dict):
                raise ValueError("Gemini returned JSON that is not an object")
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            retryable = _is_retryable_gemini_error(exc) or isinstance(exc, (json.JSONDecodeError, ValueError))
            if not retryable or attempt == 3:
                raise
            time.sleep(min(8.0, 1.0 * (2**attempt)))
    else:
        raise last_exc or RuntimeError("Gemini evaluation failed")

    total_input = 0
    total_output = 0
    total_thinking = 0
    if response is not None and hasattr(response, "usage_metadata") and response.usage_metadata:
        um = response.usage_metadata
        total_input = getattr(um, "prompt_token_count", 0) or 0
        total_output = getattr(um, "candidates_token_count", 0) or 0
        total_thinking = getattr(um, "thoughts_token_count", 0) or 0

    score = float(parsed.get("score", 0))
    score = max(0.0, min(100.0, score))
    res = {
        "score": score,
        "criteria_scores": parsed.get("criteria_scores") or {},
        "summary": parsed.get("summary") or "",
        "model": model_name,
        "input_tokens": max(1, int(total_input)),
        "output_tokens": max(1, int(total_output)),
        "thinking_tokens": max(0, int(total_thinking)),
        "latency_ms": latency_ms,
    }
    res["estimated_cost_usd"] = estimate_cost_usd(
        res["model"],
        res["input_tokens"],
        res["output_tokens"],
        res["thinking_tokens"],
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