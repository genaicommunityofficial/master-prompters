from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.services.submission_service import run_batch_evaluator, run_evaluator


def _gemini_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.usage_metadata = None
    return resp


def _settings(**overrides):
    base = {
        "gemini_api_key": "test-key",
        "gemini_model": "gemini-3.6-flash",
        "gemini_thinking_level": "minimal",
        "gemini_max_output_tokens": 512,
        "gemini_request_timeout_ms": 60_000,
    }
    base.update(overrides)
    return type("S", (), base)()


def _patch_eval(monkeypatch, client: MagicMock, **settings_overrides):
    monkeypatch.setattr(
        "app.services.submission_service.ensure_gemini_configured",
        lambda: None,
    )
    monkeypatch.setattr("app.config.settings", _settings(**settings_overrides))
    monkeypatch.setattr(
        "app.services.submission_service._get_gemini_client",
        lambda: client,
    )
    monkeypatch.setattr("app.services.submission_service.time.sleep", lambda _s: None)


def _config_from_call(client: MagicMock):
    call = client.models.generate_content.call_args
    assert call is not None
    return call.kwargs.get("config") or (call.args[1] if len(call.args) > 1 else None)


def _contents_from_call(client: MagicMock) -> str:
    call = client.models.generate_content.call_args
    assert call is not None
    if "contents" in call.kwargs:
        return str(call.kwargs["contents"])
    return str(call.args[0]) if call.args else ""


def _thinking_level(config) -> str:
    thinking = getattr(config, "thinking_config", None)
    if thinking is not None:
        level = getattr(thinking, "thinking_level", None)
        if level is not None:
            return str(level).split(".")[-1].lower()
    if isinstance(config, dict):
        raw = (config.get("thinking_config") or {}).get("thinking_level")
        return str(raw or "").split(".")[-1].lower()
    return ""


def test_each_prompt_is_its_own_gemini_call(monkeypatch):
    client = MagicMock()

    def fake_generate(**kwargs):
        text = str(kwargs.get("contents") or "")
        if "alpha prompt text" in text:
            return _gemini_response(
                '{"score": 70, "criteria_scores": {"clarity": 70}, "summary": "first"}'
            )
        if "beta prompt text" in text:
            return _gemini_response(
                '{"score": 91, "criteria_scores": {"clarity": 91}, "summary": "second"}'
            )
        raise AssertionError(f"unexpected prompt: {text}")

    client.models.generate_content.side_effect = fake_generate
    _patch_eval(monkeypatch, client)

    out = run_batch_evaluator(
        [{"prompt_text": "alpha prompt text"}, {"prompt_text": "beta prompt text"}],
        {"title": "Meme Generation", "description": "Create a meme"},
        {},
        criteria_md="RUBRIC_UNIQUE markdown",
        concurrency=2,
    )

    assert [round(r["score"]) for r in out] == [70, 91]
    assert client.models.generate_content.call_count == 2
    contents = []
    for call in client.models.generate_content.call_args_list:
        body = call.kwargs.get("contents") if call.kwargs else None
        if body is None and call.args:
            body = call.args[0]
        contents.append(str(body))
    assert any("alpha prompt text" in b and "beta prompt text" not in b for b in contents)
    assert any("beta prompt text" in b and "alpha prompt text" not in b for b in contents)
    assert all("PROMPT_1" not in b and "PROMPT_0" not in b for b in contents)


def test_single_evaluator_uses_json_object(monkeypatch):
    client = MagicMock()
    client.models.generate_content.return_value = _gemini_response(
        '{"score": 55, "criteria_scores": {}, "summary": "ok"}'
    )
    _patch_eval(monkeypatch, client)
    result = run_evaluator("hello world", {"title": "Q"}, {})
    assert result["score"] == 55
    assert result["model"] == "gemini-3.6-flash"
    assert client.models.generate_content.call_count == 1
    call = client.models.generate_content.call_args
    assert call.kwargs.get("model") == "gemini-3.6-flash" or (
        call.args and call.args[0] == "gemini-3.6-flash"
    )


def test_rate_limit_is_retried(monkeypatch):
    client = MagicMock()
    client.models.generate_content.side_effect = [
        Exception("429 Resource exhausted"),
        _gemini_response('{"score": 40, "criteria_scores": {}, "summary": "retry"}'),
    ]
    _patch_eval(monkeypatch, client)
    result = run_evaluator("prompt", {"title": "Q"}, {})
    assert result["score"] == 40
    assert client.models.generate_content.call_count == 2


def test_thinking_config_defaults_to_minimal(monkeypatch):
    client = MagicMock()
    client.models.generate_content.return_value = _gemini_response(
        '{"score": 10, "criteria_scores": [], "summary": "ok"}'
    )
    _patch_eval(monkeypatch, client)
    run_evaluator("prompt", {"title": "Q"}, {})
    config = _config_from_call(client)
    assert config is not None
    assert _thinking_level(config) == "minimal"
    max_tokens = getattr(config, "max_output_tokens", None)
    if max_tokens is None and isinstance(config, dict):
        max_tokens = config.get("max_output_tokens")
    assert max_tokens == 512
    mime = getattr(config, "response_mime_type", None)
    if mime is None and isinstance(config, dict):
        mime = config.get("response_mime_type")
    assert mime == "application/json"
    schema = getattr(config, "response_schema", None)
    if schema is None and isinstance(config, dict):
        schema = config.get("response_schema")
    assert schema is not None
    blob = json.dumps(schema if isinstance(schema, dict) else getattr(schema, "model_json_schema", lambda: {})()).lower()
    assert "additionalproperties" not in blob


def test_criteria_array_is_normalized_to_dict(monkeypatch):
    client = MagicMock()
    client.models.generate_content.return_value = _gemini_response(
        '{"score": 80, "criteria_scores": [{"name": "clarity", "score": 70}, {"name": "creativity", "score": 90}], "summary": "ok"}'
    )
    _patch_eval(monkeypatch, client)
    result = run_evaluator("prompt", {"title": "Q"}, {})
    assert result["criteria_scores"] == {"clarity": 70.0, "creativity": 90.0}


def test_schema_error_is_not_retried(monkeypatch):
    client = MagicMock()
    client.models.generate_content.side_effect = Exception(
        "additionalProperties is only supported in Gemini Enterprise Agent Platform mode, "
        "not in Gemini Developer API mode."
    )
    _patch_eval(monkeypatch, client)
    with pytest.raises(Exception, match="additionalProperties"):
        run_evaluator("prompt", {"title": "Q"}, {})
    assert client.models.generate_content.call_count == 1


def test_thinking_level_env_override(monkeypatch):
    client = MagicMock()
    client.models.generate_content.return_value = _gemini_response(
        '{"score": 10, "criteria_scores": {}, "summary": "ok"}'
    )
    _patch_eval(monkeypatch, client, gemini_thinking_level="low")
    run_evaluator("prompt", {"title": "Q"}, {})
    assert _thinking_level(_config_from_call(client)) == "low"


def test_rubric_lives_in_system_instruction_not_user_contents(monkeypatch):
    client = MagicMock()
    client.models.generate_content.return_value = _gemini_response(
        '{"score": 70, "criteria_scores": {"clarity": 70}, "summary": "ok"}'
    )
    _patch_eval(monkeypatch, client)
    run_evaluator(
        "alpha prompt text",
        {"title": "Meme Generation", "description": "Create a meme"},
        {},
        criteria_md="RUBRIC_UNIQUE markdown",
    )
    contents = _contents_from_call(client)
    config = _config_from_call(client)
    system = getattr(config, "system_instruction", None)
    if system is None and isinstance(config, dict):
        system = config.get("system_instruction")
    system_s = str(system or "")
    assert "alpha prompt text" in contents
    assert "RUBRIC_UNIQUE" not in contents
    assert "Create a meme" not in contents
    assert "RUBRIC_UNIQUE" in system_s
    assert "Create a meme" in system_s
    assert "alpha prompt text" not in system_s


def test_gemini_client_sets_request_timeout(monkeypatch):
    created: dict = {}

    class FakeClient:
        def __init__(self, **kwargs):
            created.update(kwargs)

    monkeypatch.setattr("app.config.settings", _settings())
    monkeypatch.setattr("google.genai.Client", FakeClient)
    from app.services import submission_service as ss

    ss._reset_gemini_client()
    client = ss._get_gemini_client()
    assert isinstance(client, FakeClient)
    http = created.get("http_options")
    timeout = getattr(http, "timeout", None)
    if timeout is None and isinstance(http, dict):
        timeout = http.get("timeout")
    assert timeout == 60_000
    ss._reset_gemini_client()
