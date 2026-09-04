"""Tests for the test seeding service."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services import test_seeding_service as ts


class TestPromptGeneration:
    def test_generates_correct_word_count(self):
        prompts = ts.generate_prompts_for_category(
            category_number=1,
            category_title="Meme Generation",
            category_description="Create an original, engaging, and humorous AI-generated meme prompt.",
            count=5,
            target_words=500,
        )
        assert len(prompts) == 5
        for p in prompts:
            words = len(p.split())
            assert 450 <= words <= 600, f"Expected ~500 words, got {words}"

    def test_prompts_differ_per_category(self):
        p1 = ts.generate_prompts_for_category(1, "Meme", "Meme desc", count=2, target_words=500)
        p2 = ts.generate_prompts_for_category(2, "Art", "Art desc", count=2, target_words=500)
        assert p1[0] != p2[0]

    def test_prompts_differ_per_participant(self):
        prompts_a = ts.generate_prompts_for_category(1, "Meme", "Meme desc", count=3, target_words=500, seed_offset=0)
        prompts_b = ts.generate_prompts_for_category(1, "Meme", "Meme desc", count=3, target_words=500, seed_offset=7919)
        assert set(prompts_a) != set(prompts_b)


class TestSeeding:
    @patch("app.services.test_seeding_service.db")
    def test_seed_returns_correct_counts(self, mock_db):
        mock_store = MagicMock()
        mock_db.return_value = mock_store
        result = ts.seed_test_data(participant_count=10)
        assert result["participants"] == 10
        assert result["submissions"] == 10
        assert result["responses"] == 50  # 10 x 5 categories

    @patch("app.services.test_seeding_service.db")
    def test_seed_inserts_participants(self, mock_db):
        mock_store = MagicMock()
        mock_db.return_value = mock_store
        ts.seed_test_data(participant_count=3)
        table_names = [c.args[0] for c in mock_store.table.call_args_list]
        assert "pc_participants" in table_names

    @patch("app.services.test_seeding_service.db")
    def test_seed_creates_submissions_and_responses(self, mock_db):
        mock_store = MagicMock()
        mock_db.return_value = mock_store
        ts.seed_test_data(participant_count=5)
        table_names = [c.args[0] for c in mock_store.table.call_args_list]
        assert "pc_submissions" in table_names
        assert "pc_responses" in table_names
