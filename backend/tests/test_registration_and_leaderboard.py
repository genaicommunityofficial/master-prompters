"""Tests for registration-number login, admin roster, and the per-category leaderboard."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services import admin_registration_service
from app.services.auth_service import AuthError, login_with_qr_message, login_with_registration_number


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
        "login_count": 0,
        "is_pipeline_tester": False,
    }
    row.update(overrides)
    return row


class TestRegistrationNumberLogin:
    @patch("app.services.auth_service.db")
    def test_pipeline_tester_returns_token(self, mock_db):
        store = MagicMock()
        mock_db.return_value = store
        comp = MagicMock()
        comp.data = [{"status": "OPEN", "qr_event_id": None}]
        part = MagicMock()
        part.data = [_participant(is_pipeline_tester=True, qr_token="GENAI_QR_MANUAL_X")]
        nosub = MagicMock()
        nosub.data = []

        store.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = comp
        store.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.side_effect = [
            part,
            nosub,
        ]

        result = login_with_registration_number("23BCE0001", "competition_2026")
        assert result["requires_qr"] is False
        assert result["token"]
        assert result["participant"]["display_name"] == "Ada Lovelace"

    @patch("app.services.auth_service.db")
    def test_second_login_blocked_while_session_live(self, mock_db):
        store = MagicMock()
        mock_db.return_value = store
        comp = MagicMock()
        comp.data = [{"status": "OPEN", "qr_event_id": None}]
        part = MagicMock()
        part.data = [
            _participant(
                is_pipeline_tester=False,
                qr_token="GENAI_QR_MANUAL_X",
                session_token_hash="abc",
                session_expires_at="2099-01-01T00:00:00+00:00",
            )
        ]
        nosub = MagicMock()
        nosub.data = []

        store.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = comp
        store.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.side_effect = [
            part,
            nosub,
        ]

        with pytest.raises(AuthError, match="already signed in"):
            login_with_registration_number("23BCE0001", "competition_2026")

    @patch("app.services.auth_service.db")
    def test_event_registrant_requires_qr(self, mock_db):
        store = MagicMock()
        mock_db.return_value = store
        comp = MagicMock()
        comp.data = [{"status": "OPEN", "id": "competition_2026", "qr_event_id": "evt"}]
        nobody = MagicMock()
        nobody.data = []
        event_reg = MagicMock()
        event_reg.data = [{"full_name": "Ada", "vit_registration_number": "23BCE0001", "event_id": "evt"}]

        def table(name):
            t = MagicMock()
            if name == "pc_competitions":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = comp
            elif name == "pc_participants":
                t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = nobody
                t.select.return_value.eq.return_value.execute.return_value = nobody
            else:
                t.select.return_value.ilike.return_value.eq.return_value.limit.return_value.execute.return_value = event_reg
            return t

        store.table.side_effect = table
        result = login_with_registration_number("23BCE0001", "competition_2026")
        assert result["requires_qr"] is True
        assert result["token"] is None

    @patch("app.services.auth_service.settings")
    @patch("app.services.auth_service.db")
    def test_not_found_raises(self, mock_db, mock_settings):
        mock_settings.qr_event_id = ""
        store = MagicMock()
        mock_db.return_value = store
        comp = MagicMock()
        comp.data = [{"status": "OPEN", "qr_event_id": None}]
        nobody = MagicMock()
        nobody.data = []

        def table(name):
            t = MagicMock()
            if name == "pc_competitions":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = comp
            else:
                t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = nobody
                t.select.return_value.eq.return_value.execute.return_value = nobody
                t.select.return_value.ilike.return_value.limit.return_value.execute.return_value = nobody
            return t

        store.table.side_effect = table
        with pytest.raises(AuthError) as exc:
            login_with_registration_number("NOTFOUND", "competition_2026")
        assert "not registered" in str(exc.value).lower()

    @patch("app.services.auth_service.db")
    def test_closed_competition_rejected(self, mock_db):
        store = MagicMock()
        mock_db.return_value = store
        comp = MagicMock()
        comp.data = [{"status": "CLOSED"}]
        store.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = comp
        with pytest.raises(AuthError):
            login_with_registration_number("23BCE0001", "competition_2026")

    @patch("app.services.auth_service.db")
    def test_dropped_participant_cannot_login(self, mock_db):
        store = MagicMock()
        mock_db.return_value = store
        comp = MagicMock()
        comp.data = [{"status": "OPEN", "qr_event_id": None}]
        part = MagicMock()
        part.data = [
            _participant(
                status="DISQUALIFIED",
                is_pipeline_tester=True,
                qr_token="GENAI_QR_MANUAL_X",
            )
        ]

        store.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = comp
        store.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = part

        with pytest.raises(AuthError, match="dropped"):
            login_with_registration_number("23BCE0001", "competition_2026")

    @patch("app.services.auth_service.settings")
    @patch("app.services.auth_service.db")
    def test_dropped_participant_cannot_qr_login(self, mock_db, mock_settings):
        mock_settings.qr_event_id = ""
        store = MagicMock()
        mock_db.return_value = store
        comp = MagicMock()
        comp.data = [{"status": "OPEN", "qr_event_id": None, "id": "competition_2026"}]
        qr = MagicMock()
        qr.data = [{
            "id": str(uuid.uuid4()),
            "qr_token": "GENAI_QR_ABC",
            "vit_registration_number": "23BCE0001",
            "registration_status": "verified",
            "full_name": "Ada",
        }]
        dropped = MagicMock()
        dropped.data = [_participant(status="DISQUALIFIED", qr_token="GENAI_QR_ABC")]

        def table(name):
            t = MagicMock()
            if name == "pc_competitions":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = comp
            elif name == "registrations":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = qr
            else:
                t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = dropped
            return t

        store.table.side_effect = table
        with pytest.raises(AuthError, match="dropped"):
            login_with_qr_message("GENAI_QR_ABC", "competition_2026", "23BCE0001")


class TestQrMatchesRegistration:
    @patch("app.services.auth_service.settings")
    @patch("app.services.auth_service.db")
    def test_mismatched_qr_rejected(self, mock_db, mock_settings):
        mock_settings.qr_event_id = ""
        store = MagicMock()
        mock_db.return_value = store
        comp = MagicMock()
        comp.data = [{"status": "OPEN", "qr_event_id": None, "id": "competition_2026"}]
        qr = MagicMock()
        qr.data = [{
            "id": str(uuid.uuid4()),
            "qr_token": "GENAI_QR_ABC",
            "vit_registration_number": "23BCE9999",
            "registration_status": "verified",
            "full_name": "Other",
        }]

        def table(name):
            t = MagicMock()
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
                comp if name == "pc_competitions" else qr
            )
            return t

        store.table.side_effect = table
        with pytest.raises(AuthError) as exc:
            login_with_qr_message("GENAI_QR_ABC", "competition_2026", "23BCE0001")
        assert "does not match" in str(exc.value).lower()


class TestAdminRegistration:
    @patch("app.services.admin_registration_service.db")
    def test_register_success(self, mock_db):
        store = MagicMock()
        mock_db.return_value = store
        store.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        created = _participant(qr_token="GENAI_QR_MANUAL_X")
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


class TestDropParticipant:
    @patch("app.services.admin_registration_service.db")
    def test_drop_existing_marks_disqualified_without_touching_registrations(self, mock_db):
        store = MagicMock()
        mock_db.return_value = store
        row = _participant()
        empty = MagicMock()
        empty.data = []
        found = MagicMock()
        found.data = [row]
        updated = MagicMock()
        updated.data = [{**row, "status": "DISQUALIFIED"}]
        writes: list[tuple[str, str]] = []

        def table(name):
            t = MagicMock()
            if name == "registrations":
                t.update.side_effect = AssertionError("must not update registrations")
                t.insert.side_effect = AssertionError("must not insert registrations")
                t.delete.side_effect = AssertionError("must not delete registrations")
                return t

            def _update(payload):
                writes.append((name, "update"))
                assert payload["status"] == "DISQUALIFIED"
                assert payload["session_token_hash"] is None
                chain = MagicMock()
                chain.eq.return_value.eq.return_value.execute.return_value = updated
                chain.eq.return_value.execute.return_value = updated
                return chain

            t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = found
            t.update.side_effect = _update
            return t

        store.table.side_effect = table
        out = admin_registration_service.drop_participant("competition_2026", row["id"])
        assert out["success"] is True
        assert out["id"] == row["id"]
        assert writes == [("pc_participants", "update")]

    @patch("app.services.admin_registration_service.db")
    def test_drop_event_only_inserts_stub_and_does_not_write_registrations(self, mock_db):
        store = MagicMock()
        mock_db.return_value = store
        event_id = str(uuid.uuid4())
        event_reg = {
            "id": event_id,
            "qr_token": "GENAI_QR_LIVE",
            "vit_registration_number": "23BCE0001",
            "full_name": "Ada Lovelace",
            "personal_email": "ada@example.com",
            "college_email": None,
        }
        nobody = MagicMock()
        nobody.data = []
        created = _participant(
            registration_id=event_id,
            qr_token="GENAI_QR_LIVE",
            status="DISQUALIFIED",
        )
        inserted = MagicMock()
        inserted.data = [created]
        writes: list[str] = []

        def table(name):
            t = MagicMock()
            if name == "registrations":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [event_reg]
                t.update.side_effect = AssertionError("must not update registrations")
                t.insert.side_effect = AssertionError("must not insert registrations")
                t.delete.side_effect = AssertionError("must not delete registrations")
                return t
            t.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = nobody
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = nobody

            def _insert(payload):
                writes.append("insert")
                assert payload["status"] == "DISQUALIFIED"
                assert payload["qr_token"] == "GENAI_QR_LIVE"
                assert payload["registration_id"] == event_id
                chain = MagicMock()
                chain.execute.return_value = inserted
                return chain

            t.insert.side_effect = _insert
            return t

        store.table.side_effect = table
        out = admin_registration_service.drop_participant("competition_2026", f"reg:{event_id}")
        assert out["success"] is True
        assert writes == ["insert"]

    @patch("app.services.admin_registration_service.db")
    def test_drop_tester_rejected(self, mock_db):
        store = MagicMock()
        mock_db.return_value = store
        tester = _participant(is_pipeline_tester=True, registration_number="abhinavkumarsaksena")
        store.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            tester
        ]
        with pytest.raises(admin_registration_service.RegistrationError, match="tester"):
            admin_registration_service.drop_participant("competition_2026", tester["id"])


class TestRoster:
    @patch("app.services.admin_registration_service.fetch_all")
    @patch("app.services.admin_registration_service.db")
    def test_live_roster_merges_event_and_hides_testers(self, mock_db, mock_fetch):
        store = MagicMock()
        mock_db.return_value = store
        store.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"qr_event_id": "evt"}
        ]
        event_id = str(uuid.uuid4())
        logged = _participant(
            registration_id=event_id,
            registration_number="23BCE0001",
            login_count=2,
            last_login_at="2026-01-02T00:00:00Z",
        )
        tester = _participant(is_pipeline_tester=True, registration_number="abhinavkumarsaksena")
        extra = _participant(
            qr_token="GENAI_QR_MANUAL_Z",
            registration_number="ADMIN01",
            display_name="Walk-in",
            login_count=0,
        )

        def fake_fetch(table, select, eq=None, order=None, descending=False):
            if table == "pc_participants":
                return [logged, tester, extra]
            if table == "pc_submissions":
                return [{"id": "s1", "participant_id": logged["id"], "status": "SUBMITTED", "total_score": None}]
            if table == "registrations":
                return [{
                    "id": event_id,
                    "full_name": "Ada Lovelace",
                    "vit_registration_number": "23BCE0001",
                }]
            return []

        mock_fetch.side_effect = fake_fetch
        out = admin_registration_service.list_roster("competition_2026")
        assert out["show_login"] is True
        numbers = {r["registration_number"] for r in out["participants"]}
        assert "23BCE0001" in numbers
        assert "ADMIN01" in numbers
        assert "abhinavkumarsaksena" not in numbers
        event_row = next(r for r in out["participants"] if r["registration_number"] == "23BCE0001")
        assert event_row["logged_in"] is True
        assert event_row["source"] == "event"
        added = next(r for r in out["participants"] if r["source"] == "added")
        assert added["logged_in"] is False

    @patch("app.services.admin_registration_service.fetch_all")
    @patch("app.services.admin_registration_service.db")
    def test_live_roster_hides_dropped(self, mock_db, mock_fetch):
        store = MagicMock()
        mock_db.return_value = store
        store.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"qr_event_id": "evt"}
        ]
        event_id = str(uuid.uuid4())
        dropped = _participant(
            registration_id=event_id,
            registration_number="23BCE0001",
            status="DISQUALIFIED",
        )
        extra = _participant(
            qr_token="GENAI_QR_MANUAL_Z",
            registration_number="ADMIN01",
            display_name="Walk-in",
        )

        def fake_fetch(table, select, eq=None, order=None, descending=False):
            if table == "pc_participants":
                return [dropped, extra]
            if table == "pc_submissions":
                return []
            if table == "registrations":
                return [{
                    "id": event_id,
                    "full_name": "Ada Lovelace",
                    "vit_registration_number": "23BCE0001",
                }]
            return []

        mock_fetch.side_effect = fake_fetch
        out = admin_registration_service.list_roster("competition_2026")
        numbers = {r["registration_number"] for r in out["participants"]}
        assert "23BCE0001" not in numbers
        assert "ADMIN01" in numbers

    @patch("app.services.admin_registration_service.fetch_all")
    @patch("app.services.admin_registration_service.db")
    def test_test_roster_hides_dropped(self, mock_db, mock_fetch):
        kept = _participant(display_name="Keep", registration_number="T1")
        dropped = _participant(display_name="Gone", registration_number="T2", status="DISQUALIFIED")
        mock_fetch.side_effect = lambda table, *a, **k: (
            [kept, dropped] if table == "pc_participants" else []
        )
        out = admin_registration_service.list_roster("competition_test")
        names = {r["display_name"] for r in out["participants"]}
        assert names == {"Keep"}

    @patch("app.services.admin_registration_service.fetch_all")
    @patch("app.services.admin_registration_service.db")
    def test_test_roster_hides_login(self, mock_db, mock_fetch):
        mock_fetch.side_effect = lambda table, *a, **k: (
            [_participant(display_name="Dataset User", registration_number=None)]
            if table == "pc_participants"
            else []
        )
        out = admin_registration_service.list_roster("competition_test")
        assert out["show_login"] is False
        assert out["logged_in"] is None
        assert out["participants"][0]["logged_in"] is None
        assert out["participants"][0]["source"] == "dataset"


class TestLeaderboardCategories:
    @patch("app.services.leaderboard_service.db")
    def test_get_leaderboard_includes_categories_and_average(self, mock_db):
        from app.services import leaderboard_service as svc

        class R:
            def __init__(self, data):
                self.data = data

        responses = [
            R([{"leaderboard_visible": True, "status": "OPEN"}]),
            R([{
                "id": "sub-1", "total_score": 420.0, "rank": 1, "participant_id": "p-1",
            }]),
            R([{"id": "p-1", "display_name": "Ada", "is_pipeline_tester": False}]),
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

    @patch("app.services.leaderboard_service._category_scores_by_submission")
    @patch("app.services.leaderboard_service.db")
    def test_pipeline_tester_excluded(self, mock_db, mock_cats):
        from app.services import leaderboard_service as svc

        mock_cats.return_value = {}

        class R:
            def __init__(self, data):
                self.data = data

        responses = [
            R([{"leaderboard_visible": True, "status": "OPEN"}]),
            R([
                {"id": "sub-1", "total_score": 500.0, "rank": 1, "participant_id": "tester"},
                {"id": "sub-2", "total_score": 100.0, "rank": 2, "participant_id": "real"},
            ]),
            R([
                {"id": "tester", "display_name": "Pipeline tester", "is_pipeline_tester": True},
                {"id": "real", "display_name": "Prince", "is_pipeline_tester": False},
            ]),
        ]
        seq = iter(responses)
        store = MagicMock()
        store.table.side_effect = lambda name: _ScriptedTable(name, seq)
        mock_db.return_value = store
        data = svc.get_leaderboard("competition_2026")
        assert len(data["entries"]) == 1
        assert data["entries"][0]["display_name"] == "Prince"
        assert data["entries"][0]["rank"] == 1

    @patch("app.services.leaderboard_service._category_scores_by_submission")
    @patch("app.services.leaderboard_service.db")
    def test_leaderboard_caps_at_50(self, mock_db, mock_cats):
        from app.services import leaderboard_service as svc

        mock_cats.return_value = {}

        class R:
            def __init__(self, data):
                self.data = data

        subs = [
            {"id": f"s{i}", "total_score": float(500 - i), "rank": i, "participant_id": f"p{i}"}
            for i in range(51)
        ]
        parts = [
            {"id": f"p{i}", "display_name": f"P{i}", "is_pipeline_tester": False}
            for i in range(51)
        ]
        seq = iter([
            R([{"leaderboard_visible": True, "status": "OPEN"}]),
            R(subs),
            R(parts),
        ])
        store = MagicMock()
        store.table.side_effect = lambda name: _ScriptedTable(name, seq)
        mock_db.return_value = store
        data = svc.get_leaderboard("competition_2026")
        assert len(data["entries"]) == 50
        assert data["entries"][0]["display_name"] == "P0"
        assert data["entries"][-1]["display_name"] == "P49"

    @patch("app.services.leaderboard_service._category_scores_by_submission")
    @patch("app.services.leaderboard_service.db")
    def test_leaderboard_includes_registration_number(self, mock_db, mock_cats):
        from app.services import leaderboard_service as svc

        mock_cats.return_value = {}

        class R:
            def __init__(self, data):
                self.data = data

        seq = iter([
            R([{"leaderboard_visible": True, "status": "OPEN"}]),
            R([{"id": "s1", "total_score": 420.0, "rank": 1, "participant_id": "p1"}]),
            R([{
                "id": "p1",
                "display_name": "Ada",
                "is_pipeline_tester": False,
                "registration_number": "23BCE0001",
            }]),
        ])
        store = MagicMock()
        store.table.side_effect = lambda name: _ScriptedTable(name, seq)
        mock_db.return_value = store
        data = svc.get_leaderboard("competition_2026")
        assert data["entries"][0]["registration_number"] == "23BCE0001"


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
