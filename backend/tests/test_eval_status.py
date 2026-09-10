"""Tests for eval cost calculation, progress aggregation, and the participation funnel."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services import eval_cost, leaderboard_service as lb_svc
from app.services.eval_status_service import FunnelMigrationError, get_participation_funnel


class TestEvalCost:
    @patch("app.services.eval_cost._prices_for")
    def test_estimate_from_lookup_prices(self, mock_prices):
        mock_prices.return_value = {"input": 0.0003, "output": 0.0025, "thinking": 0.0035}
        cost = eval_cost.estimate_cost_usd("gemini-2.5-flash", 1000, 1000, 500)
        assert cost == pytest.approx(0.0003 + 0.0025 + 0.00175)

    def test_unknown_model_is_free(self):
        assert eval_cost.estimate_cost_usd("unknown-model", 100, 100, 100) == 0.0

    def test_summarize_derives_cost_for_null_stored(self, monkeypatch):
        # Stored estimated_cost_usd is None -> derive from tokens x price.
        monkeypatch.setattr(
            eval_cost,
            "estimate_cost_usd",
            lambda model, i, o, t: 0.5,
        )
        summary = eval_cost.summarize_cost(
            [
                {
                    "model": "gemini-2.5-flash",
                    "input_tokens": 100,
                    "output_tokens": 200,
                    "thinking_tokens": 50,
                    "estimated_cost_usd": None,
                }
            ]
        )
        assert summary["total_evaluations"] == 1
        assert summary["estimated_cost_usd"] == 0.5
        assert summary["per_model"]["gemini-2.5-flash"]["cost_usd"] == 0.5

    def test_summarize_uses_stored_cost_when_present(self, monkeypatch):
        def boom(*a):
            raise AssertionError("should not derive when stored cost exists")

        monkeypatch.setattr(eval_cost, "estimate_cost_usd", boom)
        summary = eval_cost.summarize_cost(
            [
                {
                    "model": "gemini-2.5-flash",
                    "input_tokens": 100,
                    "output_tokens": 100,
                    "thinking_tokens": 0,
                    "estimated_cost_usd": 0.123456,
                }
            ]
        )
        assert summary["estimated_cost_usd"] == 0.123456


def _row(data, count=None):
    r = MagicMock(data=data)
    if count is not None:
        r.count = count
    return r


class _Table:
    """Fluent fake: every builder call returns self; execute() yields the row."""

    def __init__(self, ret):
        self._ret = ret

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def range(self, *a, **k): return self

    def execute(self):
        return self._ret


class TestEvalProgress:
    @patch("app.services.eval_status_service.db")
    @patch("app.db.db")
    @patch("app.services.eval_status_service.run_svc.get_status")
    def test_progress_basics(self, mock_status, mock_db_db, mock_db):
        mock_status.return_value = {"status": "running", "competition_id": "c1", "started_at": None, "completed": 2, "failed": 0, "enqueued": 3, "processed": 2, "accepted": True, "finished_at": None, "error_message": None, "batch_size": 8, "concurrency": 4, "max_retries": 3}

        store = MagicMock()

        def fake_table(name):
            if name == "pc_competitions":
                return _Table(_row([{"status": "OPEN", "leaderboard_visible": False}]))
            if name == "pc_participants":
                return _Table(_row([
                    {"id": "p1", "status": "SUBMITTED", "registration_number": "23BCE0001", "is_pipeline_tester": False},
                ], count=1))
            if name == "pc_submissions":
                return _Table(_row([
                    {"id": "s1", "status": "SUBMITTED", "total_score": None, "participant_id": "p1"},
                ]))
            if name == "pc_responses":
                return _Table(_row([
                    {"id": "r1", "question_id": "q1"},
                    {"id": "r2", "question_id": "q2"},
                ]))
            if name == "pc_evaluation_jobs":
                return _Table(_row([
                    {"status": "COMPLETED", "last_error": None, "attempt_count": 1, "response_id": "r1"},
                ]))
            if name == "pc_evaluations":
                return _Table(_row([
                    {"response_id": "r1", "score": 88, "model": "gemini-2.5-flash",
                     "input_tokens": 100, "output_tokens": 200, "thinking_tokens": 50,
                     "estimated_cost_usd": None},
                ]))
            if name == "pc_questions":
                return _Table(_row([
                    {"id": "q1", "question_number": 1, "title": "Meme"},
                    {"id": "q2", "question_number": 2, "title": "Art"},
                ]))
            raise AssertionError(f"unexpected table {name}")

        store.table.side_effect = fake_table
        mock_db.return_value = store
        mock_db_db.return_value = store

        from app.services.eval_status_service import get_eval_progress
        out = get_eval_progress("c1")
        t = out["totals"]
        assert t["responses"] == 2
        assert t["evaluated"] == 1
        assert t["pending"] == 1
        assert t["progress_pct"] == 50.0
        assert t["job_failed"] == 0
        assert out["jobs"]["COMPLETED"] == 1
        assert out["per_category"]["q1"]["evaluated"] == 1
        assert out["cost"]["total_evaluations"] == 1
        assert out["run"] is not None

    @patch("app.services.eval_status_service.db")
    @patch("app.db.db")
    @patch("app.services.eval_status_service.run_svc.get_status")
    def test_progress_excludes_pipeline_tester(self, mock_status, mock_db_db, mock_db):
        mock_status.return_value = {"status": "idle"}
        store = MagicMock()

        def fake_table(name):
            if name == "pc_competitions":
                return _Table(_row([{"status": "OPEN", "leaderboard_visible": True}]))
            if name == "pc_participants":
                return _Table(_row([
                    {
                        "id": "p-tester",
                        "status": "SUBMITTED",
                        "registration_number": "abhinavkumarsaksena",
                        "is_pipeline_tester": False,
                    },
                    {
                        "id": "p-real",
                        "status": "REGISTERED",
                        "registration_number": "25BMR10015",
                        "is_pipeline_tester": False,
                    },
                ], count=2))
            if name == "pc_submissions":
                return _Table(_row([
                    {"id": "s-tester", "status": "COMPLETED", "total_score": 0.0, "participant_id": "p-tester"},
                ]))
            if name == "pc_responses":
                return _Table(_row([
                    {"id": "r1", "question_id": "q1"},
                    {"id": "r2", "question_id": "q1"},
                    {"id": "r3", "question_id": "q1"},
                    {"id": "r4", "question_id": "q1"},
                    {"id": "r5", "question_id": "q1"},
                ]))
            if name == "pc_evaluation_jobs":
                return _Table(_row([{"status": "COMPLETED", "last_error": None, "attempt_count": 1, "response_id": "r1"}]))
            if name == "pc_evaluations":
                return _Table(_row([
                    {"response_id": rid, "score": 0.0, "model": "gemini-3.6-flash",
                     "input_tokens": 1, "output_tokens": 1, "thinking_tokens": 0,
                     "estimated_cost_usd": 0}
                    for rid in ("r1", "r2", "r3", "r4", "r5")
                ]))
            if name == "pc_questions":
                return _Table(_row([{"id": "q1", "question_number": 1, "title": "Meme"}]))
            raise AssertionError(f"unexpected table {name}")

        store.table.side_effect = fake_table
        mock_db.return_value = store
        mock_db_db.return_value = store

        from app.services.eval_status_service import get_eval_progress
        out = get_eval_progress("c1")
        assert out["totals"]["evaluated"] == 0
        assert out["totals"]["responses"] == 0
        assert out["totals"]["submitted"] == 0
        assert out["per_category"]["q1"]["evaluated"] == 0


class TestParticipationFunnel:
    @patch("app.services.eval_status_service.db")
    def test_funnel_counts(self, mock_db):
        store = MagicMock()

        p1 = {"id": "p1", "status": "REGISTERED", "login_count": 1, "last_login_at": "t", "registration_number": None, "display_name": "A", "email": "a@x", "registration_id": None, "qr_token": "x"}
        p2 = {"id": "p2", "status": "REGISTERED", "login_count": 0, "last_login_at": None, "registration_number": "R2", "display_name": "B", "email": "b@x", "registration_id": None, "qr_token": "y"}

        def fake_table(name):
            if name == "pc_participants":
                return _Table(_row([p1, p2]))
            if name == "pc_submissions":
                return _Table(_row([{"id": "s1", "participant_id": "p1", "status": "COMPLETED", "total_score": 300}]))
            raise AssertionError(name)

        store.table.side_effect = fake_table
        mock_db.return_value = store

        out = get_participation_funnel("c1")
        assert out["registered"] == 2
        assert out["logged_in"] == 1
        assert out["submitted"] == 1
        assert out["completed"] == 1
        assert out["funnel"]["logged_in"]["count"] == 1
        assert out["funnel"]["submitted"]["pct_of_logged_in"] == 100.0

    @patch("app.services.eval_status_service.db")
    def test_missing_migration_raises_guide(self, mock_db):
        store = MagicMock()
        store.table.side_effect = Exception("column login_count does not exist")
        mock_db.return_value = store
        with pytest.raises(FunnelMigrationError) as exc:
            get_participation_funnel("c1")
        assert "0003" in str(exc.value)


class TestLeaderboardBypass:
    @patch("app.services.leaderboard_service.db")
    def test_ignore_visibility_shows_hidden(self, mock_db):
        class R:
            def __init__(self, data):
                self.data = data

        store = MagicMock()
        responses = [
            R([{"leaderboard_visible": False, "status": "OPEN"}]),  # comp hidden
            R([{"id": "s1", "total_score": 100.0, "rank": 1, "participant_id": "p1"}]),  # subs
            R([{"id": "p1", "display_name": "Ada"}]),  # participants
            R([{"competition_id": "c1"}]),
            R([{"id": "q1", "question_number": 1}]),
            R([{"id": "r1", "question_id": "q1", "submission_id": "s1"}]),
            R([{"response_id": "r1", "score": 95, "created_at": "2026-01-01T00:00:00Z"}]),
        ]
        seq = iter(responses)

        class Table:
            def select(self, *a): return self
            def eq(self, *a): return self
            @property
            def not_(self): return self
            def is_(self, *a): return self
            def in_(self, *a): return self
            def limit(self, *a): return self
            def order(self, *a, **k): return self
            def execute(self): return next(seq)

        store.table.return_value = Table()
        mock_db.return_value = store

        data = lb_svc.get_leaderboard("c1", ignore_visibility=True)
        assert data["visible"] is True
        assert data["published"] is False
        assert data["entries"][0]["display_name"] == "Ada"

        # Without the bypass the same hidden competition stays hidden.
        seq2 = iter([R([{"leaderboard_visible": False, "status": "CLOSED"}])])

        class T2:
            def select(self, *a): return self
            def eq(self, *a): return self
            def limit(self, *a): return self
            def execute(self): return next(seq2)

        store.table.return_value = T2()
        assert lb_svc.get_leaderboard("c1")["visible"] is False


class TestDashboardFromProgress:
    def test_maps_eval_jobs_onto_dashboard_kpis(self):
        from app.services.admin_service import dashboard_from_progress

        dash = dashboard_from_progress(
            {
                "competition_id": "c1",
                "competition_status": "OPEN",
                "totals": {
                    "participants": 10,
                    "submissions": 8,
                    "submitted": 7,
                    "completed": 3,
                    "failed": 1,
                    "job_failed": 4,
                    "responses": 35,
                    "evaluated": 20,
                    "pending": 15,
                    "progress_pct": 57.1,
                    "avg_score": 80.0,
                    "median_score": 81.0,
                    "highest_score": 90.0,
                    "lowest_score": 70.0,
                },
                "jobs": {
                    "QUEUED": 2,
                    "PROCESSING": 1,
                    "RETRY": 1,
                    "COMPLETED": 20,
                    "FAILED": 4,
                    "total": 28,
                },
                "per_category": {
                    "q1": {
                        "question_number": 1,
                        "title": "Meme",
                        "stored": 7,
                        "evaluated": 4,
                    }
                },
            }
        )
        assert dash["evaluation_failed"] == 4
        assert dash["awaiting_eval"] == 15
        assert dash["retrying"] == 2
        assert dash["total_prompts"] == 35
        assert dash["failed"] == 1
        assert dash["per_category"]["q1"]["stored"] == 7


class TestScopedCompetition:
    def test_allows_live_and_test(self):
        from app.api.admin import TEST_COMPETITION_ID, _scoped_competition

        payload = {"competition_id": "competition_2026"}
        assert _scoped_competition(payload, None) == "competition_2026"
        assert _scoped_competition(payload, TEST_COMPETITION_ID) == TEST_COMPETITION_ID

    def test_rejects_other_competition(self):
        from fastapi import HTTPException

        from app.api.admin import _scoped_competition

        payload = {"competition_id": "competition_2026"}
        try:
            _scoped_competition(payload, "competition_other")
            raise AssertionError("expected HTTPException")
        except HTTPException as exc:
            assert exc.status_code == 403


class TestFetchInPaging:
    @patch("app.db.db")
    def test_pages_past_rest_row_cap(self, mock_db):
        from app.db import REST_PAGE, fetch_in

        pages = [
            [{"id": f"r{i}"} for i in range(REST_PAGE)],
            [{"id": "r-last"}],
        ]

        class Builder:
            def __init__(self):
                self.calls = 0

            def select(self, *a, **k):
                return self

            def in_(self, *a, **k):
                return self

            def order(self, *a, **k):
                return self

            def range(self, start, end):
                return self

            def execute(self):
                data = pages[min(self.calls, len(pages) - 1)]
                self.calls += 1
                row = MagicMock()
                row.data = data
                return row

        store = MagicMock()
        store.table.return_value = Builder()
        mock_db.return_value = store

        rows = fetch_in("pc_responses", "id", "submission_id", ["s1"], page_size=200)
        assert len(rows) == REST_PAGE + 1
        assert rows[-1]["id"] == "r-last"
