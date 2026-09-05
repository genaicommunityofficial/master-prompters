from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.submission_service import run_batch_evaluator, run_evaluator


def _gemini_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.usage_metadata = None
    return resp


@patch("google.generativeai.GenerativeModel")
@patch("google.generativeai.configure")
def test_each_prompt_is_its_own_gemini_call(mock_configure, mock_model_cls, monkeypatch):
    monkeypatch.setattr(
        "app.services.submission_service.ensure_gemini_configured",
        lambda: None,
    )
    monkeypatch.setattr("app.config.settings", type("S", (), {"gemini_api_key": "test-key"})())
    inst = mock_model_cls.return_value
    inst.generate_content.side_effect = [
        _gemini_response('{"score": 70, "criteria_scores": {"clarity": 70}, "summary": "first"}'),
        _gemini_response('{"score": 91, "criteria_scores": {"clarity": 91}, "summary": "second"}'),
    ]

    out = run_batch_evaluator(
        [{"prompt_text": "alpha prompt text"}, {"prompt_text": "beta prompt text"}],
        {"title": "Meme Generation", "description": "Create a meme"},
        {},
        concurrency=2,
    )

    assert [round(r["score"]) for r in out] == [70, 91]
    assert inst.generate_content.call_count == 2
    bodies = [c.args[0] for c in inst.generate_content.call_args_list]
    assert len(bodies) == 2
    assert any("alpha prompt text" in b and "beta prompt text" not in b for b in bodies)
    assert any("beta prompt text" in b and "alpha prompt text" not in b for b in bodies)
    assert all("PROMPT_1" not in b and "PROMPT_0" not in b for b in bodies)
    mock_configure.assert_called()


@patch("google.generativeai.GenerativeModel")
@patch("google.generativeai.configure")
def test_single_evaluator_uses_json_object(mock_configure, mock_model_cls, monkeypatch):
    monkeypatch.setattr(
        "app.services.submission_service.ensure_gemini_configured",
        lambda: None,
    )
    monkeypatch.setattr("app.config.settings", type("S", (), {"gemini_api_key": "test-key"})())
    inst = mock_model_cls.return_value
    inst.generate_content.return_value = _gemini_response(
        '{"score": 55, "criteria_scores": {}, "summary": "ok"}'
    )
    result = run_evaluator("hello world", {"title": "Q"}, {})
    assert result["score"] == 55
    assert result["model"] == "gemini-3.6-flash"
    assert mock_model_cls.call_args.args[0] == "gemini-3.6-flash"
    assert inst.generate_content.call_count == 1
    kwargs = inst.generate_content.call_args
    assert kwargs is not None


@patch("google.generativeai.GenerativeModel")
@patch("google.generativeai.configure")
def test_rate_limit_is_retried(mock_configure, mock_model_cls, monkeypatch):
    monkeypatch.setattr(
        "app.services.submission_service.ensure_gemini_configured",
        lambda: None,
    )
    monkeypatch.setattr("app.config.settings", type("S", (), {"gemini_api_key": "test-key"})())
    monkeypatch.setattr("app.services.submission_service.time.sleep", lambda _s: None)
    inst = mock_model_cls.return_value
    inst.generate_content.side_effect = [
        Exception("429 Resource exhausted"),
        _gemini_response('{"score": 40, "criteria_scores": {}, "summary": "retry"}'),
    ]
    result = run_evaluator("prompt", {"title": "Q"}, {})
    assert result["score"] == 40
    assert inst.generate_content.call_count == 2
