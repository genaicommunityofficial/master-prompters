from unittest.mock import MagicMock

import pytest

from app.services.eval_run_service import (
    TEST_COMPETITION_ID,
    _run_thread,
    clamp_eval_params,
    get_logs,
    get_status,
    pause as pause_eval,
    requeue_failed_jobs,
    reset_for_tests,
    reset_test_eval_results,
    start as start_eval,
)
from app.services.submission_service import ensure_gemini_configured, job_payloads_for_responses


def test_job_payloads_use_response_id_not_question_id():
    rows = [
        {"id": "resp-1", "question_id": "tq1"},
        {"id": "resp-2", "question_id": "tq2"},
    ]
    jobs = job_payloads_for_responses(rows)
    assert [j["response_id"] for j in jobs] == ["resp-1", "resp-2"]
    assert all(j["status"] == "QUEUED" for j in jobs)
    assert all(j["model"] == "gemini-3.6-flash" for j in jobs)


def test_missing_api_key_raises_config_error(monkeypatch):
    class EmptySettings:
        gemini_api_key = ""

    monkeypatch.setattr("app.config.settings", EmptySettings())
    with pytest.raises(Exception) as exc:
        ensure_gemini_configured()
    assert "Gemini API key" in str(exc.value)


def test_eval_start_refuses_missing_key(monkeypatch):
    monkeypatch.setattr("app.config.settings", type("S", (), {"gemini_api_key": ""})())
    with pytest.raises(Exception) as exc:
        start_eval(competition_id="competition_test", batch_size=4, concurrency=2)
    assert "Gemini API key" in str(exc.value)


def test_eval_params_are_capped():
    batch, concurrency, retries = clamp_eval_params(batch_size=999, concurrency=999, max_retries=99)
    assert batch <= 50
    assert concurrency <= 16
    assert retries <= 5


def test_eval_start_refuses_when_running(monkeypatch):
    reset_for_tests()
    monkeypatch.setattr("app.config.settings", type("S", (), {"gemini_api_key": "test-key"})())
    monkeypatch.setattr("app.services.eval_run_service._spawn", lambda **kwargs: None)
    first = start_eval(competition_id="competition_test", batch_size=4, concurrency=2)
    assert first["status"] == "running"
    second = start_eval(competition_id="competition_test")
    assert second.get("accepted") is False
    reset_for_tests()


def test_reset_test_eval_rejects_live():
    with pytest.raises(ValueError):
        reset_test_eval_results("competition_2026")


def test_reset_test_eval_clears_scores_and_requeues(monkeypatch):
    ops: list[tuple] = []

    class Table:
        def __init__(self, name: str):
            self.name = name
            self._op = None

        def select(self, *a, **k):
            self._op = "select"
            return self

        def eq(self, *a, **k):
            return self

        def in_(self, col, ids):
            ops.append((self._op or "in", self.name, col, list(ids)))
            return self

        def delete(self):
            self._op = "delete"
            ops.append(("delete", self.name))
            return self

        def update(self, payload):
            self._op = "update"
            ops.append(("update", self.name, payload))
            return self

        def execute(self):
            if self.name == "pc_submissions" and self._op == "select":
                return MagicMock(data=[{"id": "sub-1"}])
            if self.name == "pc_responses" and self._op == "select":
                return MagicMock(data=[{"id": "r1"}, {"id": "r2"}])
            return MagicMock(data=[])

    monkeypatch.setattr("app.services.eval_run_service.db", lambda: MagicMock(table=Table))
    n = reset_test_eval_results(TEST_COMPETITION_ID)
    assert n == 2
    assert any(op[0] == "delete" and op[1] == "pc_evaluations" for op in ops)
    job_updates = [op for op in ops if op[0] == "update" and op[1] == "pc_evaluation_jobs"]
    assert job_updates
    assert job_updates[0][2]["status"] == "QUEUED"
    sub_updates = [op for op in ops if op[0] == "update" and op[1] == "pc_submissions"]
    assert sub_updates
    assert sub_updates[0][2]["status"] == "SUBMITTED"
    assert sub_updates[0][2]["total_score"] is None


def test_run_thread_resets_test_and_scores_already_queued(monkeypatch):
    reset_for_tests()
    monkeypatch.setattr("app.services.eval_run_service.time.sleep", lambda _s: None)
    monkeypatch.setattr("app.services.eval_run_service.reset_test_eval_results", lambda cid: 3)
    monkeypatch.setattr("app.services.eval_run_service.enqueue_pending_jobs", lambda cid: 0)
    monkeypatch.setattr("app.services.eval_run_service._queued_job_count", lambda cid: 3)
    monkeypatch.setattr("app.services.eval_run_service._job_counts", lambda cid: (3, 0))

    rounds = [["j1", "j2", "j3"], [], []]

    def fake_ids(cid, limit=10):
        return rounds.pop(0) if rounds else []

    monkeypatch.setattr(
        "app.services.evaluation_service.get_queued_job_ids_for_competition",
        fake_ids,
    )

    batches = {"n": 0}

    def fake_batch(**kwargs):
        batches["n"] += 1
        on_progress = kwargs.get("on_progress")
        if on_progress:
            on_progress({"ok": True, "title": "Meme", "question_number": 1, "score": 80})
            on_progress({"ok": False, "title": "Essay", "question_number": 2, "error": "timeout"})
            on_progress({"ok": True, "title": "Code", "question_number": 3, "score": 91.5})
        return 2

    monkeypatch.setattr("app.services.evaluation_service.process_queued_batch", fake_batch)
    _run_thread(competition_id=TEST_COMPETITION_ID, batch_size=16, concurrency=8, max_retries=3)
    assert batches["n"] == 1
    messages = [e["message"] for e in get_logs(since=0, limit=200)["logs"]]
    joined = "\n".join(messages)
    assert "from the beginning" in joined.lower()
    assert any("score 80" in m for m in messages)
    assert any("timeout" in m for m in messages)
    reset_for_tests()


def test_run_thread_does_not_reset_live(monkeypatch):
    reset_for_tests()
    reset_called: list[str] = []
    monkeypatch.setattr(
        "app.services.eval_run_service.reset_test_eval_results",
        lambda cid: reset_called.append(cid) or 0,
    )
    monkeypatch.setattr("app.services.eval_run_service.enqueue_pending_jobs", lambda cid: 0)
    monkeypatch.setattr("app.services.eval_run_service._queued_job_count", lambda cid: 0)
    monkeypatch.setattr("app.services.eval_run_service._job_counts", lambda cid: (10, 0))
    _run_thread(
        competition_id="competition_2026",
        batch_size=16,
        concurrency=8,
        max_retries=3,
    )
    assert reset_called == []
    reset_for_tests()


def test_pause_rejects_when_idle():
    reset_for_tests()
    out = pause_eval()
    assert out.get("accepted") is False
    assert out["status"] == "idle"


def test_pause_signals_running_run(monkeypatch):
    reset_for_tests()
    monkeypatch.setattr("app.config.settings", type("S", (), {"gemini_api_key": "test-key"})())
    monkeypatch.setattr("app.services.eval_run_service._spawn", lambda **kwargs: None)
    start_eval(competition_id="competition_test", batch_size=4, concurrency=2)
    out = pause_eval()
    assert out.get("accepted") is True
    assert out["status"] == "pausing"
    reset_for_tests()


def test_start_resume_does_not_reset_test(monkeypatch):
    reset_for_tests()
    monkeypatch.setattr("app.config.settings", type("S", (), {"gemini_api_key": "test-key"})())
    spawned: list[dict] = []
    monkeypatch.setattr("app.services.eval_run_service._spawn", lambda **kwargs: spawned.append(kwargs))
    start_eval(competition_id="competition_test", mode="resume")
    assert spawned[0]["reset_scores"] is False
    assert spawned[0]["requeue_failed"] is False
    reset_for_tests()


def test_start_retry_failed_flags_requeue(monkeypatch):
    reset_for_tests()
    monkeypatch.setattr("app.config.settings", type("S", (), {"gemini_api_key": "test-key"})())
    spawned: list[dict] = []
    monkeypatch.setattr("app.services.eval_run_service._spawn", lambda **kwargs: spawned.append(kwargs))
    start_eval(competition_id="competition_test", mode="retry_failed")
    assert spawned[0]["reset_scores"] is False
    assert spawned[0]["requeue_failed"] is True
    reset_for_tests()


def test_run_thread_pauses_after_current_batch(monkeypatch):
    reset_for_tests()
    from app.services import eval_run_service as ers

    monkeypatch.setattr("app.services.eval_run_service.time.sleep", lambda _s: None)
    monkeypatch.setattr("app.services.eval_run_service.enqueue_pending_jobs", lambda cid: 0)
    monkeypatch.setattr("app.services.eval_run_service._queued_job_count", lambda cid: 2)
    monkeypatch.setattr("app.services.eval_run_service._job_counts", lambda cid: (0, 0))
    rounds = [["j1"], ["j2"], [], []]

    def fake_ids(cid, limit=10):
        return rounds.pop(0) if rounds else []

    monkeypatch.setattr(
        "app.services.evaluation_service.get_queued_job_ids_for_competition",
        fake_ids,
    )
    batches = {"n": 0}

    def fake_batch(**kwargs):
        batches["n"] += 1
        ers._halt.set()
        return 1

    monkeypatch.setattr("app.services.evaluation_service.process_queued_batch", fake_batch)
    _run_thread(
        competition_id=TEST_COMPETITION_ID,
        batch_size=16,
        concurrency=8,
        max_retries=3,
        reset_scores=False,
    )
    assert batches["n"] == 1
    assert get_status()["status"] == "paused"
    reset_for_tests()


def test_run_thread_resume_skips_test_reset(monkeypatch):
    reset_for_tests()
    reset_called: list[str] = []
    monkeypatch.setattr("app.services.eval_run_service.time.sleep", lambda _s: None)
    monkeypatch.setattr(
        "app.services.eval_run_service.reset_test_eval_results",
        lambda cid: reset_called.append(cid) or 0,
    )
    monkeypatch.setattr("app.services.eval_run_service.enqueue_pending_jobs", lambda cid: 0)
    monkeypatch.setattr("app.services.eval_run_service._queued_job_count", lambda cid: 0)
    monkeypatch.setattr("app.services.eval_run_service._job_counts", lambda cid: (10, 2))
    _run_thread(
        competition_id=TEST_COMPETITION_ID,
        batch_size=16,
        concurrency=8,
        max_retries=3,
        reset_scores=False,
    )
    assert reset_called == []
    messages = [e["message"] for e in get_logs(since=0, limit=200)["logs"]]
    assert any("Resuming" in m or "ready to score" in m for m in messages)
    reset_for_tests()


def test_requeue_failed_jobs(monkeypatch):
    ops: list[tuple] = []

    class Table:
        def __init__(self, name: str):
            self.name = name
            self._op = None
            self._filters: dict = {}

        def select(self, *a, **k):
            self._op = "select"
            return self

        def eq(self, *a, **k):
            return self

        def in_(self, col, ids):
            self._filters[col] = list(ids)
            ops.append((self._op or "in", self.name, col, list(ids)))
            return self

        def update(self, payload):
            self._op = "update"
            ops.append(("update", self.name, payload))
            return self

        def execute(self):
            if self.name == "pc_submissions" and self._op == "select":
                return MagicMock(data=[{"id": "sub-1"}])
            if self.name == "pc_responses" and self._op == "select":
                return MagicMock(data=[{"id": "r1"}, {"id": "r2"}])
            if self.name == "pc_evaluation_jobs" and self._op == "select":
                return MagicMock(
                    data=[
                        {"id": "job-fail", "status": "FAILED"},
                        {"id": "job-ok", "status": "COMPLETED"},
                    ]
                )
            return MagicMock(data=[])

    monkeypatch.setattr("app.services.eval_run_service.db", lambda: MagicMock(table=Table))
    n = requeue_failed_jobs(TEST_COMPETITION_ID)
    assert n == 1
    job_updates = [op for op in ops if op[0] == "update" and op[1] == "pc_evaluation_jobs"]
    assert job_updates
    assert job_updates[0][2]["status"] == "QUEUED"


def test_retired_model_error_is_permanent():
    from app.services.evaluation_service import _is_permanent_failure

    assert _is_permanent_failure(
        "404 This model models/gemini-2.5-flash is no longer available to new users."
    )
    assert not _is_permanent_failure("429 Resource exhausted")

