from app.services import stress_test_service as svc


def test_clamp_total_caps_and_floors():
    (total,) = svc.clamp_params(total=50_000)
    assert total <= svc.MAX_TOTAL
    (total,) = svc.clamp_params(total=0)
    assert total >= 1


def test_no_concurrency_param_is_accepted():
    """The stress test no longer takes a concurrency option."""
    # start must reject concurrency confusion by signature: no 'concurrency' kw.
    import inspect

    sig = inspect.signature(svc.start)
    assert "concurrency" not in sig.parameters


def test_start_refuses_when_already_running(monkeypatch):
    svc.reset_for_tests()
    monkeypatch.setattr(svc, "_spawn", lambda **kwargs: None)
    first = svc.start(total=10, base_url="http://test")
    assert first["status"] == "running"
    second = svc.start(total=10, base_url="http://test")
    assert second["status"] == "running"
    assert second.get("accepted") is False
    svc.reset_for_tests()


def test_summarize_results():
    rows = [
        {"ok": True, "ms": 10.0, "status": 200},
        {"ok": True, "ms": 30.0, "status": 200},
        {"ok": False, "ms": 5.0, "status": 500},
    ]
    summary = svc.summarize(rows, elapsed_s=1.0)
    assert summary["total"] == 3
    assert summary["succeeded"] == 2
    assert summary["errors"] == 1
    assert summary["req_per_s"] == 3.0


def test_make_prompt_payload_has_five_test_questions():
    prompts = svc.make_prompt_payload()
    assert len(prompts) == 5
    assert {p["question_id"] for p in prompts} == {"tq1", "tq2", "tq3", "tq4", "tq5"}
    assert all(len(p["prompt_text"]) >= 20 for p in prompts)


def test_validate_submission_accepts_test_status():
    from app.services.submission_service import validate_submission

    questions = [
        {"id": f"tq{i}", "title": f"Q{i}", "min_length": 5, "max_length": 200}
        for i in range(1, 6)
    ]
    prompts = [
        {"question_id": f"tq{i}", "prompt_text": "a long enough prompt"}
        for i in range(1, 6)
    ]
    out = validate_submission({"status": "TEST"}, questions, prompts)
    assert len(out) == 5