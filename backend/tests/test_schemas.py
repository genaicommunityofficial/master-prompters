from app.schemas.schemas import IndividualPromptRequest, PromptInput


def test_individual_prompt_requires_competition_id():
    body = IndividualPromptRequest(
        competition_id="competition_test",
        question_id="tq1",
        prompt_text="a reasonably long prompt for testing",
    )
    assert body.competition_id == "competition_test"
    assert body.question_id == "tq1"


def test_batch_prompt_input_still_validates():
    p = PromptInput(question_id="q1", prompt_text="hello world")
    assert p.question_id == "q1"
