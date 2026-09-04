from app.services.auth_service import synthetic_participant_row


def test_synthetic_participant_includes_registration_id():
    row = synthetic_participant_row("competition_2026", "e2e-ui")
    assert row["competition_id"] == "competition_2026"
    assert row["registration_id"]
    assert row["qr_token"].startswith("GENAI_QR_")
    assert row["display_name"] == "e2e-ui"
    assert row["status"] == "REGISTERED"
