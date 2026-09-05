from app.services.submission_service import ensure_gemini_configured, job_payloads_for_responses
from app.services.eval_run_service import clamp_eval_params, reset_for_tests, start as start_eval
import pytest


def test_job_payloads_use_response_id_not_question_id():
    rows = [
        {"id": "resp-1", "question_id": "tq1"},
        {"id": "resp-2", "question_id": "tq2"},
    ]
    jobs = job_payloads_for_responses(rows)
    assert [j["response_id"] for j in jobs] == ["resp-1", "resp-2"]
    assert all(j["status"] == "QUEUED" for j in jobs)


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
