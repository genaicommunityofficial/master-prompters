from __future__ import annotations

import json
import threading
import time

from app.db import db as _db_instance
from app.services import competition_service as comp_svc
from app.services.eval_cost import estimate_cost_usd
from app.services.session_guard import PROMPT_FROZEN_MSG, frozen_prompt_action

_THINKING_LEVELS = frozenset({"minimal", "low", "medium", "high"})
_gemini_lock = threading.Lock()
_gemini_client: object | None = None
_gemini_client_key: tuple[str, int] | None = None

# Gemini Developer API rejects JSON Schema `additionalProperties` (which Pydantic
# emits for dict[str, float]). Use an array of named scores instead.
JUDGE_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "score": {"type": "number"},
        "criteria_scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "score": {"type": "number"},
                },
                "required": ["name", "score"],
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["score", "criteria_scores", "summary"],
}


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

    max_length = competition.get("max_submission_length") or 2000

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
    """Insert a response, or no-op if the same text is already stored. Edits are rejected."""
    existing_response = (
        db()
        .table("pc_responses")
        .select("id, prompt_text")
        .eq("submission_id", sub_id)
        .eq("question_id", prompt["question_id"])
        .limit(1)
        .execute()
        .data
        or []
    )
    existing_text = existing_response[0].get("prompt_text") if existing_response else None
    action = frozen_prompt_action(existing_text, prompt["prompt_text"])
    if action == "keep":
        return
    if action == "reject":
        raise SubmissionError(PROMPT_FROZEN_MSG)
    payload = {
        "prompt_text": prompt["prompt_text"],
        "word_count": _word_count(prompt["prompt_text"]),
        "token_estimate": _estimate_tokens(prompt["prompt_text"]),
    }
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


def gemini_thinking_level() -> str:
    """Gemini 3 thinking depth. Default minimal keeps judge JSON fast and cheap."""
    from app.config import settings

    raw = str(getattr(settings, "gemini_thinking_level", "") or "minimal").strip().lower()
    return raw if raw in _THINKING_LEVELS else "minimal"


def gemini_max_output_tokens() -> int:
    from app.config import settings

    try:
        value = int(getattr(settings, "gemini_max_output_tokens", 512) or 512)
    except (TypeError, ValueError):
        return 512
    return max(64, min(value, 2048))


def gemini_request_timeout_ms() -> int:
    from app.config import settings

    try:
        value = int(getattr(settings, "gemini_request_timeout_ms", 60_000) or 60_000)
    except (TypeError, ValueError):
        return 60_000
    return max(5_000, min(value, 180_000))


def _reset_gemini_client() -> None:
    """Drop the cached client (tests, or after API key rotation)."""
    global _gemini_client, _gemini_client_key
    with _gemini_lock:
        _gemini_client = None
        _gemini_client_key = None


def _get_gemini_client():
    """Reuse one google-genai Client per process (and per API key / timeout)."""
    global _gemini_client, _gemini_client_key
    from google import genai
    from google.genai import types

    from app.config import settings

    api_key = str(getattr(settings, "gemini_api_key", "") or "")
    timeout_ms = gemini_request_timeout_ms()
    key = (api_key, timeout_ms)
    with _gemini_lock:
        if _gemini_client is None or _gemini_client_key != key:
            _gemini_client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=timeout_ms),
            )
            _gemini_client_key = key
        return _gemini_client


def ensure_gemini_configured() -> None:
    """Raises EvalConfigError unless a real Gemini API key is configured."""
    from app.config import settings

    if not settings.gemini_api_key:
        raise EvalConfigError(
            "Gemini API key is not configured on the server. "
            "Set GEMINI_API_KEY before starting an evaluation run."
        )


def _judge_system_instruction(question: dict, criteria_md: str) -> str:
    """Stable prefix: role, task, rubric, JSON rules. Participant prompt is user content."""
    question_text = question.get("description") or question.get("title") or ""
    parts = [
        "You are an expert prompt engineer evaluating one competition prompt.",
        "",
        f"## Question / Task\n{question_text}",
    ]
    if criteria_md:
        parts.extend(["", f"## Evaluation Criteria (Rubric)\n{criteria_md}"])
    parts.extend(
        [
            "",
            "## Instructions",
            "Score this prompt independently against the criteria. Do not compare it to other prompts.",
            "Return a JSON object with exactly these keys:",
            '  - "score": number 0-100 (overall score)',
            '  - "criteria_scores": array of objects {"name": rubric dimension, "score": number 0-100}',
            '  - "summary": string (one sentence explaining the score)',
            "Return ONLY the JSON object.",
        ]
    )
    return "\n".join(parts)


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
    if "additionalproperties" in msg or "not in gemini developer api" in msg:
        return False
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


def _normalize_criteria_scores(raw: object) -> dict[str, float]:
    """Accept Gemini array [{name, score}] or a legacy {dimension: score} object."""
    out: dict[str, float] = {}
    if isinstance(raw, dict):
        items = raw.items()
        for key, value in items:
            try:
                out[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        return out
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("criterion") or item.get("key")
            score = item.get("score")
            if name is None or score is None:
                continue
            try:
                out[str(name)] = float(score)
            except (TypeError, ValueError):
                continue
    return out


def _gemini_evaluate_one(
    item: dict,
    question: dict,
    evaluation_config: dict,
) -> dict:
    """One competition prompt → one Gemini JSON score. Retries transient API errors."""
    from google.genai import types

    model_name = gemini_model_name()
    client = _get_gemini_client()
    criteria_md = evaluation_config.get("criteria_md", "") or ""
    prompt_text = item["prompt_text"]
    system_instruction = _judge_system_instruction(question, criteria_md)
    config = types.GenerateContentConfig(
        temperature=0,
        response_mime_type="application/json",
        max_output_tokens=gemini_max_output_tokens(),
        system_instruction=system_instruction,
        thinking_config=types.ThinkingConfig(thinking_level=gemini_thinking_level()),
        response_schema=JUDGE_RESPONSE_SCHEMA,
    )

    last_exc: Exception | None = None
    raw = ""
    latency_ms = 0
    response = None
    parsed: dict = {}
    for attempt in range(4):
        t0 = time.monotonic()
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt_text,
                config=config,
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
            raw = (getattr(response, "text", None) or "").strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            parsed_obj = json.loads(raw)
            if isinstance(parsed_obj, list):
                if len(parsed_obj) != 1 or not isinstance(parsed_obj[0], dict):
                    raise ValueError("Gemini returned a JSON array instead of one score object")
                parsed_obj = parsed_obj[0]
            if not isinstance(parsed_obj, dict):
                raise ValueError("Gemini returned JSON that is not an object")
            parsed = parsed_obj
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
        "criteria_scores": _normalize_criteria_scores(parsed.get("criteria_scores")),
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
    _upsert_response(sub_id, prompt_data)

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