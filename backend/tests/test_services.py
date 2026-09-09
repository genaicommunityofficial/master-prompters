from app.services.auth_service import normalize_qr_message
from app.services.competition_service import to_public_question
from app.services.submission_service import _estimate_tokens, _word_count, validate_submission


def test_normalize_plain_token():
    assert normalize_qr_message("GENAI_QR_ABC123") == "GENAI_QR_ABC123"


def test_normalize_embedded_url():
    assert normalize_qr_message("https://evt/genai?qr=GENAI_QR_XYZ7890") == "GENAI_QR_XYZ7890"


def test_normalize_empty():
    assert normalize_qr_message("") == ""


def test_word_count():
    assert _word_count("  hello   world foo  ") == 3
    assert _word_count("") == 0


def test_estimate_tokens():
    assert _estimate_tokens("abcd") == 1
    assert _estimate_tokens("") == 1


def test_validate_wrong_count():
    try:
        validate_submission({"status": "OPEN"}, [], [])
        assert False, "expected error"
    except Exception:
        pass


def test_validate_not_open():
    try:
        validate_submission({"status": "DRAFT"}, [], [{"question_id": "q", "prompt_text": "x"}])
        assert False, "expected error"
    except Exception:
        pass


def test_validate_length_bounds():
    questions = [
        {"id": f"q{i}", "title": f"Q{i}", "min_length": 5, "max_length": 200} for i in range(1, 6)
    ]
    prompts = [
        {"question_id": "q1", "prompt_text": "   hi   "},
        {"question_id": "q2", "prompt_text": "a long enough prompt"},
        {"question_id": "q3", "prompt_text": "a long enough prompt"},
        {"question_id": "q4", "prompt_text": "a long enough prompt"},
        {"question_id": "q5", "prompt_text": "a long enough prompt"},
    ]
    comp = {"status": "OPEN"}
    try:
        validate_submission(comp, questions, prompts)
        assert False, "expected too-short error"
    except Exception as e:
        assert "at least" in str(e)


def test_public_question_uses_canonical_prompt_limits():
    q = to_public_question(
        {
            "id": "q1",
            "question_number": 1,
            "title": "Meme",
            "description": None,
            "max_length": 500,
            "min_length": 10,
        }
    )
    assert q["min_length"] == 20
    assert q["max_length"] == 2000
