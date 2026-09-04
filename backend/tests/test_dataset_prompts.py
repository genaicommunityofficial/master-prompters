"""Tests for the authored test-prompt dataset module."""
from __future__ import annotations

import re

from app.data import test_prompts as tp
from app.services import test_seeding_service as ts


class TestDatasetPrompts:
    def test_prompts_meet_word_count(self):
        for cat in ts.CATEGORIES:
            p = tp.dataset_prompts_for_category(cat["number"], 1, target_words=500, seed_offset=0)[0]
            assert len(p.split()) >= 500, f"Category {cat['number']} below 500 words: {len(p.split())}"

    def test_no_unfilled_placeholders(self):
        for pidx in (0, 7, 49, 123, 299):
            for cat in ts.CATEGORIES:
                p = tp.dataset_prompts_for_category(
                    cat["number"], 1, target_words=500, seed_offset=pidx * 7919 + cat["number"] * 13
                )[0]
                assert "{" not in p and "}" not in p, f"Unfilled placeholder: {p[:120]}"

    def test_all_1500_are_unique(self):
        seen: set[str] = set()
        for pidx in range(300):
            for cat in ts.CATEGORIES:
                p = tp.dataset_prompts_for_category(
                    cat["number"], 1, target_words=500, seed_offset=pidx * 7919 + cat["number"] * 13
                )[0]
                seen.add(p)
        assert len(seen) == 300 * len(ts.CATEGORIES)

    def test_iter_participant_prompts_yields_categories_per_participant(self):
        cats = ts.CATEGORIES
        batches = list(tp.iter_participant_prompts(3, cats, target_words=500))
        assert len(batches) == 3
        for batch in batches:
            assert len(batch) == 5
            for p in batch:
                assert len(p.split()) >= 500

    def test_placeholders_themselves_are_valid(self):
        # Every placeholder referenced by skeletons/craft notes/elaborations has
        # a value in FILL_INS so nothing can be left dangling.
        text = " ".join(
            [s for skeletons in tp.SKELETONS.values() for s in skeletons]
            + [c for notes in tp.CRAFT_NOTES.values() for c in notes]
            + [e for pool in tp.ELABORATIONS.values() for e in pool]
        )
        used = set(re.findall(r"\{([^}]+)\}", text))
        assert used <= set(tp.FILL_INS.keys()), f"Missing fill-ins: {used - set(tp.FILL_INS.keys())}"
