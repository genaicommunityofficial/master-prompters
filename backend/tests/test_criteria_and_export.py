"""Tests for per-category markdown evaluation criteria + close-submissions gate."""

import pytest

from app.services import admin_analytics_service as aa_svc
from app.services import eval_criteria_service as crit
from app.services import submission_service


def test_content_hash_is_stable():
    h1 = crit.content_hash("## Rules\n\nBe specific.")
    h2 = crit.content_hash("## Rules\n\nBe specific.")
    assert h1 == h2
    assert len(h1) == 64


def test_inject_md_is_included_for_matching_question():
    prompt = "Some prompt text."
    question = {"id": "q1", "question_number": 1, "title": "Meme", "evaluation_config": {}}
    rubric = "# Judging\n\nScore creativity 0-40."

    # Criteria present for question 1 -> included.
    criteria_map = {1: rubric}
    out = crit.apply_criteria(criteria_map, prompt, question)
    assert rubric in out
    assert prompt in out

    # No criteria for the question -> unchanged.
    out2 = crit.apply_criteria({}, prompt, question)
    assert "Judging" not in out2
    assert out2 == prompt


def test_close_status_rejects_submission():
    from app.services.submission_service import validate_submission

    questions = [
        {"id": f"q{i}", "title": f"Q{i}", "min_length": 5, "max_length": 200}
        for i in range(1, 6)
    ]
    prompts = [
        {"question_id": f"q{i}", "prompt_text": "a long enough prompt"}
        for i in range(1, 6)
    ]
    try:
        validate_submission({"status": "CLOSED"}, questions, prompts)
        raised = False
    except submission_service.SubmissionError:
        raised = True
    assert raised is True


def test_build_export_orders_blocks_by_category(monkeypatch):
    """Export rows grouped in strict category 1..5 order, per-category CSV."""
    samples = [
        {"category": 5, "prompt_text": "q5"},
        {"category": 2, "prompt_text": "q2"},
        {"category": 1, "prompt_text": "q1"},
        {"category": 4, "prompt_text": "q4"},
        {"category": 3, "prompt_text": "q3"},
    ]

    def fake_build(competition_id, category=None):
        if category is not None:
            return [r for r in samples if r["category"] == category], [], "x.csv"
        return list(reversed(samples)), [], "all.csv"

    monkeypatch.setattr(aa_svc, "build_export", fake_build)
    rows = aa_svc.order_export_blocks(samples, by_category=False)
    cats = [r["category"] for r in rows]
    assert cats == [1, 2, 3, 4, 5]


def test_criteria_service_upserts_with_hash(monkeypatch):
    """Upsert computes content_hash and stores it."""

    class FakeStore:
        def __init__(self):
            self.rows = []

        def table(self, name):
            assert name == "pc_eval_criteria"
            return FakeTable(self.rows)

    class FakeTable:
        def __init__(self, rows):
            self.rows = rows

        def upsert(self, payload):
            self.rows.append(payload)
            return self

        def execute(self):
            class R:
                data = self.rows
            return R()

    store = FakeStore()
    crit._upsert_criteria(store, competition_id="c1", question_number=2,
                          file_name="x.md", content_md="## X\n\nbody")
    assert store.rows[0]["question_number"] == 2
    assert len(store.rows[0]["content_hash"]) == 64


def test_copy_criteria_writes_each_source_row(monkeypatch):
    written: list[tuple] = []

    monkeypatch.setattr(
        crit,
        "get_criteria_for_competition",
        lambda cid: {1: {"file_name": "a.md", "content_md": "# A"}, 2: {"file_name": "b.md", "content_md": "# B"}}
        if cid == "live"
        else {},
    )

    def fake_upsert(store, *, competition_id, question_number, file_name, content_md):
        written.append((competition_id, question_number, file_name, content_md))
        return {}

    monkeypatch.setattr(crit, "_upsert_criteria", fake_upsert)
    monkeypatch.setattr(crit, "db", lambda: object())
    assert crit.copy_criteria("live", "competition_test") == 2
    assert written[0][0] == "competition_test"
    assert {w[1] for w in written} == {1, 2}


def test_upsert_rejected_when_locked(monkeypatch):
    monkeypatch.setattr(
        crit,
        "get_criteria_for_competition",
        lambda cid: {1: {"locked": True, "content_md": "# old"}},
    )
    with pytest.raises(crit.CriteriaLockedError, match="locked"):
        crit.upsert_criteria(
            competition_id="c1",
            question_number=1,
            file_name="criteria.md",
            content_md="# new",
        )


def test_lock_requires_saved_content(monkeypatch):
    monkeypatch.setattr(crit, "get_criteria_for_competition", lambda cid: {})
    with pytest.raises(crit.CriteriaError, match="Save"):
        crit.set_criteria_locked("c1", 1, True)