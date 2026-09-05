#!/usr/bin/env python3
"""Populate the isolated TEST competition with a hand-authored prompt dataset.

The 1500 (~500-word each) prompts are authored offline by the codegen harness
(bottom `backend/app/data/test_prompts.py`) and inserted into the TEST
competition DB. No runtime LLM / API key is required.

Usage:
  python scripts/populate_test_dataset.py --total 300            # replace TEST data
  python scripts/populate_test_dataset.py --total 100 --append    # add more
  python scripts/populate_test_dataset.py --total 50 --dry-run    # preview counts

Requires backend deps and backend/.env (SUPABASE_URL / SERVICE_ROLE_KEY).
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / "backend" / ".env")

from app.data.test_prompts import iter_participant_prompts  # noqa: E402
from app.db import db  # noqa: E402
from app.services import test_seeding_service  # noqa: E402

CATEGORIES = test_seeding_service.CATEGORIES


def wipe_test_data() -> None:
    test_seeding_service.cleanup_test_data()


def main() -> int:
    parser = argparse.ArgumentParser(description="Populate the TEST competition with authored prompts.")
    parser.add_argument("--total", type=int, default=300, help="Number of participants (prompts x5).")
    parser.add_argument("--append", action="store_true", help="Append instead of replacing TEST data.")
    parser.add_argument("--dry-run", action="store_true", help="Print counts without writing.")
    parser.add_argument("--target-words", type=int, default=80, help="Word target before fitting to 20–2000 characters.")
    args = parser.parse_args()

    if args.total < 1 or args.total > 2000:
        print("Error: --total must be between 1 and 2000.")
        return 1

    store = db()

    if not args.append:
        if not args.dry_run:
            wipe_test_data()
            print("Cleared existing TEST competition data.")
        else:
            print("dry-run: would clear existing TEST competition data.")

    if args.dry_run:
        print(
            f"dry-run: would prepare {args.total} participants, "
            f"{args.total * len(CATEGORIES)} responses, "
            f"~{args.target_words} words each."
        )
        return 0

    test_seeding_service._ensure_test_competition(store)
    print(
        f"Preparing {args.total} participants, "
        f"{args.total * len(CATEGORIES)} responses, "
        f"~{args.target_words} words each."
    )

    participant_ids: list[str] = []
    for pidx in range(args.total):
        pid = str(uuid.uuid4())
        participant_ids.append(pid)
        store.table("pc_participants").insert({
            "id": pid,
            "competition_id": test_seeding_service.TEST_COMPETITION_ID,
            "registration_id": str(uuid.uuid4()),
            "qr_token": f"DS_{pid.replace('-', '')[:16]}",
            "display_name": f"Dataset User {pid[:8]}",
            "email": f"dataset-{pid[:8]}@test.local",
            "status": "SUBMITTED",
        }).execute()

    total_responses = 0
    for pidx, prompts in enumerate(
        iter_participant_prompts(args.total, CATEGORIES, target_words=args.target_words)
    ):
        sub_id = str(uuid.uuid4())
        store.table("pc_submissions").insert({
            "id": sub_id,
            "competition_id": test_seeding_service.TEST_COMPETITION_ID,
            "participant_id": participant_ids[pidx],
            "status": "SUBMITTED",
            "submitted_at": "now()",
        }).execute()

        for cat, prompt_text in zip(CATEGORIES, prompts):
            store.table("pc_responses").insert({
                "submission_id": sub_id,
                "question_id": cat["id"],
                "prompt_text": prompt_text,
                "word_count": len(prompt_text.split()),
                "token_estimate": len(prompt_text) // 4,
            }).execute()
            total_responses += 1

        if (pidx + 1) % 25 == 0 or (pidx + 1) == args.total:
            print(f"  wrote {pidx + 1}/{args.total} participants ({total_responses} responses)")

    print(
        f"Done. {args.total} participants, {total_responses} responses "
        f"seeded into {test_seeding_service.TEST_COMPETITION_ID}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
