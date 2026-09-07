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


def test_order_export_keeps_rows_without_category():
    rows = [
        {"category": 0, "prompt_text": "uncat"},
        {"category": 1, "prompt_text": "meme"},
    ]
    ordered = aa_svc.order_export_blocks(rows)
    assert [r["prompt_text"] for r in ordered] == ["meme", "uncat"]


def test_export_keeps_test1_to_test10_together_in_natural_order():
    """Each person stays together; test1, test2, test10 — not test1, test10, test2."""
    rows = [
        {"registration_number": "test10", "display_name": "test10", "category": 1, "prompt_text": "p10-1"},
        {"registration_number": "test2", "display_name": "test2", "category": 2, "prompt_text": "p2-2"},
        {"registration_number": "test1", "display_name": "test1", "category": 5, "prompt_text": "p1-5"},
        {"registration_number": "test1", "display_name": "test1", "category": 1, "prompt_text": "p1-1"},
        {"registration_number": "test2", "display_name": "test2", "category": 1, "prompt_text": "p2-1"},
        {"registration_number": "test10", "display_name": "test10", "category": 2, "prompt_text": "p10-2"},
    ]
    ordered = aa_svc.order_export_blocks(rows)
    assert [(r["registration_number"], r["category"]) for r in ordered] == [
        ("test1", 1),
        ("test1", 5),
        ("test2", 1),
        ("test2", 2),
        ("test10", 1),
        ("test10", 2),
    ]


def test_export_registration_number_never_uses_name():
    assert aa_svc._export_registration_number({"registration_number": "23BCE0001"}, {}) == "23BCE0001"
    assert (
        aa_svc._export_registration_number(
            {"registration_number": None, "registration_id": "rid-1", "display_name": "Ada Lovelace"},
            {"rid-1": {"registration_number": "23BCE0002", "display_name": "Ada Lovelace"}},
        )
        == "23BCE0002"
    )
    assert (
        aa_svc._export_registration_number(
            {"registration_number": None, "display_name": "Ada Lovelace", "email": "ada@x"},
            {},
        )
        == ""
    )


def test_export_display_name_prefers_event_then_participant():
    assert (
        aa_svc._export_display_name(
            {"registration_id": "rid-1", "display_name": "Fallback"},
            {"rid-1": {"registration_number": "23BCE0002", "display_name": "Ada Lovelace"}},
        )
        == "Ada Lovelace"
    )
    assert aa_svc._export_display_name({"display_name": "Test User"}, {}) == "Test User"


def test_export_csv_only_has_regno_category_prompt(monkeypatch):
    monkeypatch.setattr(
        aa_svc,
        "build_export",
        lambda cid, category=None: (
            [
                {
                    "registration_number": "23BCE0001",
                    "display_name": "Ada Lovelace",
                    "category": 1,
                    "category_title": "Meme Generation",
                    "prompt_text": "a shareable meme prompt",
                }
            ],
            aa_svc.build_export_columns(cid),
            "prompts_live_all.csv",
        ),
    )
    data, columns, filename = aa_svc.build_export_csv("competition_2026")
    text = data.decode("utf-8-sig")
    header = text.splitlines()[0]
    assert header == "Reg No,Name,Category,Prompt"
    assert "23BCE0001" in text
    assert "Ada Lovelace" in text
    assert "Meme Generation" in text
    assert "a shareable meme prompt" in text
    assert "Full Name" not in text
    assert "Email" not in text
    assert filename == "prompts_live_all.csv"
    assert [c[1] for c in columns] == ["Reg No", "Name", "Category", "Prompt"]


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, data):
        self._data = list(data)

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def in_(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def range(self, start, end):
        self._data = self._data[start : end + 1]
        return self

    def execute(self):
        return _Result(self._data)


class _Store:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return _Query(self.tables.get(name, []))


def test_build_export_fills_test_competition_rows(monkeypatch):
    store = _Store(
        {
            "pc_questions": [
                {"id": "tq1", "question_number": 1, "title": "Meme Generation"},
            ],
            "pc_participants": [
                {
                    "id": "p1",
                    "status": "SUBMITTED",
                    "registration_id": "missing-event-row",
                    "registration_number": "TEST-ABC",
                    "display_name": "Test User",
                    "email": "t@x",
                    "qr_token": "x",
                }
            ],
            "pc_submissions": [{"id": "s1", "participant_id": "p1"}],
            "pc_responses": [
                {
                    "submission_id": "s1",
                    "question_id": "tq1",
                    "prompt_text": "hello meme prompt text here",
                }
            ],
            "registrations": [],
        }
    )
    monkeypatch.setattr(aa_svc, "db", lambda: store)
    rows, columns, filename = aa_svc.build_export("competition_test")
    assert filename == "prompts_test_all.csv"
    assert [c[1] for c in columns] == ["Reg No", "Name", "Category", "Prompt"]
    assert len(rows) == 1
    assert rows[0]["registration_number"] == "TEST-ABC"
    assert rows[0]["display_name"] == "Test User"
    assert rows[0]["category_title"] == "Meme Generation"
    assert rows[0]["prompt_text"] == "hello meme prompt text here"


def test_live_export_uses_event_vit_number_not_name(monkeypatch):
    store = _Store(
        {
            "pc_questions": [
                {"id": "q1", "question_number": 1, "title": "Meme Generation"},
                {"id": "q2", "question_number": 2, "title": "AI Visual Art Creation"},
            ],
            "pc_participants": [
                {
                    "id": "p1",
                    "status": "SUBMITTED",
                    "registration_id": "evt-1",
                    "registration_number": None,
                    "display_name": "Ada Lovelace",
                    "email": "ada@x",
                    "qr_token": "GENAI_QR_EVENT_ADA",
                    "is_pipeline_tester": False,
                },
                {
                    "id": "p-test1",
                    "status": "SUBMITTED",
                    "registration_id": "fake",
                    "registration_number": "test1",
                    "display_name": "test1",
                    "email": "test1",
                    "qr_token": "GENAI_QR_MANUAL_X",
                    "is_pipeline_tester": False,
                },
            ],
            "pc_submissions": [
                {"id": "s1", "participant_id": "p1"},
                {"id": "s-test", "participant_id": "p-test1"},
            ],
            "pc_responses": [
                {
                    "submission_id": "s1",
                    "question_id": "q1",
                    "prompt_text": "a shareable meme prompt",
                },
                {
                    "submission_id": "s-test",
                    "question_id": "q1",
                    "prompt_text": "should not appear",
                },
            ],
        }
    )
    monkeypatch.setattr(aa_svc, "db", lambda: store)
    monkeypatch.setattr(
        aa_svc,
        "_event_registration_lookup",
        lambda cid: {
            "evt-1": {"registration_number": "23BCE7777", "display_name": "Ada Lovelace"},
        },
    )
    rows, columns, filename = aa_svc.build_export("competition_2026")
    assert filename == "prompts_live_all.csv"
    assert [c[1] for c in columns] == ["Reg No", "Name", "Category", "Prompt"]
    assert len(rows) == 1
    assert rows[0]["registration_number"] == "23BCE7777"
    assert rows[0]["display_name"] == "Ada Lovelace"
    assert rows[0]["category_title"] == "Meme Generation"
    assert rows[0]["prompt_text"] == "a shareable meme prompt"
    assert "Ada" not in rows[0]["registration_number"]
    assert all(r["registration_number"] != "test1" for r in rows)


def test_live_export_excludes_manual_accounts_and_empty_prompts(monkeypatch):
    store = _Store(
        {
            "pc_questions": [
                {"id": "q1", "question_number": 1, "title": "Meme Generation"},
                {"id": "q2", "question_number": 2, "title": "AI Visual Art Creation"},
            ],
            "pc_participants": [
                {
                    "id": "p-test1",
                    "status": "REGISTERED",
                    "registration_id": "fake-uuid",
                    "registration_number": "test1",
                    "display_name": "test1",
                    "email": "test1",
                    "qr_token": "GENAI_QR_MANUAL_X",
                    "is_pipeline_tester": False,
                },
                {
                    "id": "p-event",
                    "status": "REGISTERED",
                    "registration_id": "evt-1",
                    "registration_number": None,
                    "display_name": "Mahi Gupta",
                    "email": "mahi@x",
                    "qr_token": "GENAI_QR_EVENT",
                    "is_pipeline_tester": False,
                },
            ],
            "pc_submissions": [],
            "pc_responses": [],
        }
    )
    monkeypatch.setattr(aa_svc, "db", lambda: store)
    monkeypatch.setattr(
        aa_svc,
        "_event_registration_lookup",
        lambda cid: {
            "evt-1": {"registration_number": "26BCE11688", "display_name": "MAHI GUPTA"},
        },
    )
    rows, _, filename = aa_svc.build_export("competition_2026")
    assert filename == "prompts_live_all.csv"
    assert rows == []


def test_live_export_strips_regno_off_event_name():
    assert aa_svc._clean_display_name("TIMON SAMNIWAR 26BCE10382", "26BCE10382") == "TIMON SAMNIWAR"
    assert aa_svc._clean_display_name("MAHI GUPTA", "26BCE11688") == "MAHI GUPTA"


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