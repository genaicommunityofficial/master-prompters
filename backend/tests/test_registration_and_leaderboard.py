"""Tests for registration-number login, admin manual registration, and the
per-category leaderboard."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services import admin_registration_service
from app.services.auth_service import AuthError, login_with_registration_number


def _participant(**overrides):
    row = {
        "id": str(uuid.uuid4()),
        "competition_id": "competition_2026",
        "registration_id": str(uuid.uuid4()),
        "qr_token": "GENAI_QR_TEST",
        "registration_number": "23BCE0001",
        "display_name": "Ada Lovelace",
        "email": "ada@example.com",
        "status": "REGISTERED",
        "created_at": "2026-01-01T00:00:00Z",
    }
    row.update(overrides)
    return row


class TestRegistrationNumberLogin:
    @patch("app.services.auth_service.db")
    def test_found_returns_token(self, mock_db):
        store = MagicMock()
        mock_db.return_value = store
        # competition status (single .eq + .limit)
        comp = MagicMock(); comp.data = [{"status": "OPEN"}]
        # participant lookup then has_submission share the two-.eq chain:
        part = MagicMock(); part.data = [_participant()]
        nosub = MagicMock(); nosub.data = []

        comp_chain = store.table.return_value.select.return_value.eq.return_value.limit.return_value
        comp_chain.execute.return_value = comp

        part_sub_chain = store.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value
        part_sub_chain.execute.side_effect = [part, nosub]

        result = login_with_registration_number("23BCE0001", "competition_2026")
        assert result["token"]
        assert result["participant"]["display_name"] == "Ada Lovelace"
        assert result["participant"]["vit_registration_number"] == "23BCE0001"
        assert result["participant"]["already_submitted"] is False

    @patch("app.services.auth_service.db")
    def test_not_found_raises_not_participated(self, mock_db):
        store = MagicMock()
        mock_db.return_value = store
        comp = MagicMock(); comp.data = [{"status": "OPEN"}]
        nobody = MagicMock(); nobody.data = []

        comp_chain = store.table.return_value.select.return_value.eq.return_value.limit.return_value
        comp_chain.execute.return_value = comp
        part_chain = store.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value
        part_chain.execute.return_value = nobody

        with pytest.raises(AuthError) as exc:
            login_with_registration_number("NOTFOUND", "competition_2026")
        assert "not registered" in str(exc.value).lower()

    @patch("app.services.auth_service.db")
    def test_closed_competition_rejected(self, mock_db):
        store = MagicMock()
        mock_db.return_value = store
        comp = MagicMock(); comp.data = [{"status": "CLOSED"}]
        comp_chain = store.table.return_value.select.return_value.eq.return_value.limit.return_value
        comp_chain.execute.return_value = comp
        with pytest.raises(AuthError):
            login_with_registration_number("23BCE0001", "competition_2026")


class TestAdminRegistration:
    @patch("app.services.admin_registration_service.db")
    def test_register_success(self, mock_db):
        store = MagicMock()
        mock_db.return_value = store
        store.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        created = _participant()
        store.table.return_value.insert.return_value.execute.return_value.data = [created]
        row = admin_registration_service.register_participant(
            "competition_2026", "23BCE0001", "Ada Lovelace", "ada@example.com"
        )
        assert row["registration_number"] == "23BCE0001"

    @patch("app.services.admin_registration_service.db")
    def test_register_missing_number_rejected(self, mock_db):
        with pytest.raises(admin_registration_service.RegistrationError):
            admin_registration_service.register_participant("competition_2026", "  ")

    @patch("app.services.admin_registration_service.db")
    def test_register_duplicate_rejected(self, mock_db):
        store = MagicMock()
        mock_db.return_value = store
        store.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            _participant()
        ]
        with pytest.raises(admin_registration_service.RegistrationError):
            admin_registration_service.register_participant("competition_2026", "23BCE0001")

    @patch("app.services.admin_registration_service.db")
    def test_list_registrations_returns_only_registered_numbers(self, mock_db):
        store = MagicMock()
        mock_db.return_value = store
        rows = MagicMock(); rows.data = [_participant()]
        store.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.order.return_value.execute.return_value = rows
        out = admin_registration_service.list_registrations("competition_2026")
        assert len(out) == 1
        assert out[0]["registration_number"] == "23BCE0001"


class TestLeaderboardCategories:
    @patch("app.services.leaderboard_service.db")
    def test_get_leaderboard_includes_categories_and_average(self, mock_db):
        from app.services import leaderboard_service as svc

        class R:
            def __init__(self, data):
                self.data = data

        # Scripted sequence of execute() responses, in call order:
        # 1. pc_competitions (leaderboard visible)
        # 2. pc_submissions (completed, ranked)
        # 3. pc_participants (bulk display-name prefetch)
        # 4. pc_submissions.single competition_id lookup (for questions)
        # 5. pc_questions (question_number map)
        # 6. pc_responses (per submission)
        # 7. pc_evaluations (scores)
        responses = [
            R([{"leaderboard_visible": True, "status": "OPEN"}]),
            R([{
                "id": "sub-1", "total_score": 420.0, "rank": 1, "participant_id": "p-1",
            }]),
            R([{"id": "p-1", "display_name": "Ada"}]),
            R([{"competition_id": "competition_2026"}]),
            R([
                {"id": "q1", "question_number": 1},
                {"id": "q2", "question_number": 2},
                {"id": "q3", "question_number": 3},
                {"id": "q4", "question_number": 4},
                {"id": "q5", "question_number": 5},
            ]),
            R([
                {"id": "r1", "question_id": "q1", "submission_id": "sub-1"},
                {"id": "r2", "question_id": "q2", "submission_id": "sub-1"},
                {"id": "r3", "question_id": "q3", "submission_id": "sub-1"},
                {"id": "r4", "question_id": "q4", "submission_id": "sub-1"},
                {"id": "r5", "question_id": "q5", "submission_id": "sub-1"},
            ]),
            R([
                {"response_id": "r1", "score": 80},
                {"response_id": "r2", "score": 85},
                {"response_id": "r3", "score": 90},
                {"response_id": "r4", "score": 75},
                {"response_id": "r5", "score": 90},
            ]),
        ]
        seq = iter(responses)

        store = MagicMock()

        def fake_table(name):
            return _ScriptedTable(name, seq)

        store.table.side_effect = fake_table
        mock_db.return_value = store

        data = svc.get_leaderboard("competition_2026")
        assert data["visible"] is True
        entry = data["entries"][0]
        assert entry["category_scores"] == {1: 80.0, 2: 85.0, 3: 90.0, 4: 75.0, 5: 90.0}
        assert entry["average_score"] == 84.0
        assert entry["total_score"] == 420.0


class _ScriptedTable:
    """Fluent fake that dispatches to a shared scripted sequence on execute()."""

    def __init__(self, name, seq):
        self._name = name
        self._seq = seq

    def select(self, *a):
        return self

    def eq(self, *a):
        return self

    @property
    def not_(self):
        return self

    def is_(self, *a):
        return self

    def in_(self, *a):
        return self

    def limit(self, *a):
        return self

    def order(self, *a, **k):
        return self

    def execute(self):
        return next(self._seq)
