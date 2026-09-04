"""Seed the TEST competition with realistic prompts for evaluation testing.

Uses the authored dataset from ``app.data.test_prompts`` to generate
unique ~500-word prompts per participant/category, seeded deterministically.
"""
from __future__ import annotations

import uuid
from typing import Any

from app.db import db
from app.data.test_prompts import dataset_prompts_for_category

TEST_COMPETITION_ID = "competition_test"

CATEGORIES = [
    {"id": "tq1", "number": 1, "title": "Meme Generation", "description": "Create an original, engaging, and humorous AI-generated meme prompt."},
    {"id": "tq2", "number": 2, "title": "AI Visual Art Creation", "description": "Transform imagination into compelling AI-generated digital artwork with a detailed prompt."},
    {"id": "tq3", "number": 3, "title": "AI Digital Storytelling / Creative Writing", "description": "Generate an engaging story or creative written piece using Generative AI."},
    {"id": "tq4", "number": 4, "title": "AI Song Factory", "description": "Create an original AI-generated song using creative prompting techniques."},
    {"id": "tq5", "number": 5, "title": "AI-Generated Poetry in Local Languages", "description": "Generate meaningful poetry in any Indian or regional language using AI."},
]


def generate_prompts_for_category(
    category_number: int,
    category_title: str,
    category_description: str,
    count: int,
    target_words: int = 500,
    seed_offset: int = 0,
) -> list[str]:
    """Backward-compatible wrapper around the new authored dataset."""
    return dataset_prompts_for_category(
        category_number, count, target_words, seed_offset
    )


def seed_test_data(participant_count: int = 50) -> dict[str, Any]:
    """Seed the TEST competition with realistic test data.

    Creates *participant_count* participants, each with a submission containing
    5 responses (one per category). Prompts are ~500 words and unique per
    participant/category combination.
    """
    store = db()
    _ensure_test_competition(store)

    participant_ids: list[str] = []
    batch: list[dict] = []
    for _ in range(participant_count):
        pid = str(uuid.uuid4())
        participant_ids.append(pid)
        batch.append({
            "id": pid,
            "competition_id": TEST_COMPETITION_ID,
            "registration_id": str(uuid.uuid4()),
            "qr_token": f"TEST_{pid.replace('-', '')[:16]}",
            "display_name": f"Test User {pid[:8]}",
            "email": f"test-{pid[:8]}@test.local",
            "status": "SUBMITTED",
        })
        if len(batch) >= 50:
            store.table("pc_participants").insert(batch).execute()
            batch = []
    if batch:
        store.table("pc_participants").insert(batch).execute()

    total_responses = 0
    for pidx, pid in enumerate(participant_ids):
        sub_id = str(uuid.uuid4())
        store.table("pc_submissions").insert({
            "id": sub_id,
            "competition_id": TEST_COMPETITION_ID,
            "participant_id": pid,
            "status": "SUBMITTED",
            "submitted_at": "now()",
        }).execute()

        for cat in CATEGORIES:
            prompts = generate_prompts_for_category(
                category_number=cat["number"],
                category_title=cat["title"],
                category_description=cat["description"],
                count=1,
                target_words=500,
                seed_offset=pidx * 7919,
            )
            prompt_text = prompts[0]
            store.table("pc_responses").insert({
                "submission_id": sub_id,
                "question_id": cat["id"],
                "prompt_text": prompt_text,
                "word_count": len(prompt_text.split()),
                "token_estimate": len(prompt_text) // 4,
            }).execute()
            total_responses += 1

    return {
        "participants": len(participant_ids),
        "submissions": len(participant_ids),
        "responses": total_responses,
    }


def _ensure_test_competition(store) -> None:
    """Ensure the TEST competition and questions exist."""
    store.table("pc_competitions").upsert({
        "id": TEST_COMPETITION_ID,
        "name": "TEST Competition",
        "slug": "test-competition",
        "description": "Isolated competition for evaluation testing.",
        "status": "TEST",
        "leaderboard_visible": False,
        "results_visible": False,
    }).execute()
    rows = [
        {
            "id": cat["id"],
            "competition_id": TEST_COMPETITION_ID,
            "question_number": cat["number"],
            "title": cat["title"],
            "description": cat["description"],
            "input_type": "textarea",
            "max_length": 2000,
            "min_length": 20,
            "display_order": cat["number"],
            "evaluation_config": {},
        }
        for cat in CATEGORIES
    ]
    store.table("pc_questions").upsert(rows).execute()


def cleanup_test_data() -> dict[str, int]:
    """Delete all TEST competition data. Returns counts of deleted rows.

    Deletes are chunked to stay within PostgREST's URL-length limits.
    """
    store = db()

    subs = (
        store.table("pc_submissions")
        .select("id")
        .eq("competition_id", TEST_COMPETITION_ID)
        .execute()
        .data or []
    )
    sub_ids = [s["id"] for s in subs]

    deleted = {"participants": 0, "submissions": 0, "responses": 0, "jobs": 0, "evaluations": 0}

    if not sub_ids:
        store.table("pc_participants").delete().eq("competition_id", TEST_COMPETITION_ID).execute()
        return deleted

    resp_ids: list[str] = []
    for chunk in _chunked(sub_ids):
        rows = (
            store.table("pc_responses")
            .select("id")
            .in_("submission_id", chunk)
            .execute()
            .data or []
        )
        resp_ids.extend(r["id"] for r in rows)

    for chunk in _chunked(resp_ids):
        store.table("pc_evaluations").delete().in_("response_id", chunk).execute()
        store.table("pc_evaluation_jobs").delete().in_("response_id", chunk).execute()
        store.table("pc_responses").delete().in_("id", chunk).execute()
    deleted["evaluations"] = len(resp_ids)
    deleted["jobs"] = len(resp_ids)
    deleted["responses"] = len(resp_ids)

    for chunk in _chunked(sub_ids):
        store.table("pc_submissions").delete().in_("id", chunk).execute()
    deleted["submissions"] = len(sub_ids)

    store.table("pc_participants").delete().eq("competition_id", TEST_COMPETITION_ID).execute()
    deleted["participants"] = len(sub_ids)

    return deleted


def _chunked(values: list[str], size: int = 200) -> list[list[str]]:
    return [values[i : i + size] for i in range(0, len(values), size)]
