"""One-time live cleanup for this project's pc_* tables only.

Keeps Prince Agrawal. Seeds the pipeline tester ``abhinavkumarsaksena``.
Deletes other live ``pc_participants`` (cascade submissions / responses / jobs).

Does NOT touch:
  - registrations / events / checkins
  - competition_test (1500-prompt dataset)

Usage:
    cd backend
    python ../scripts/cleanup_live_participants.py           # dry run
    python ../scripts/cleanup_live_participants.py --apply
"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db import db  # noqa: E402
from app.services.admin_registration_service import MANUAL_QR_PREFIX  # noqa: E402

LIVE = "competition_2026"
TESTER_REG = "abhinavkumarsaksena"


def _is_prince(row: dict) -> bool:
    blob = f"{row.get('display_name') or ''} {row.get('email') or ''} {row.get('registration_number') or ''}".lower()
    return "prince" in blob and ("agrawal" in blob or "agral" in blob or "agraval" in blob)


def _is_tester(row: dict) -> bool:
    return (row.get("registration_number") or "").strip().casefold() == TESTER_REG.casefold()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Perform deletes and the tester insert.")
    args = parser.parse_args()

    store = db()
    parts = (
        store.table("pc_participants")
        .select("id, display_name, email, registration_number")
        .eq("competition_id", LIVE)
        .execute()
        .data
        or []
    )
    # Optional flag from migration 0004 — ignore if the column is not applied yet.
    try:
        flagged = (
            store.table("pc_participants")
            .select("id, is_pipeline_tester")
            .eq("competition_id", LIVE)
            .execute()
            .data
            or []
        )
        tester_ids = {row["id"] for row in flagged if row.get("is_pipeline_tester")}
        for row in parts:
            row["is_pipeline_tester"] = row["id"] in tester_ids
    except Exception:  # noqa: BLE001
        print("Note: is_pipeline_tester column not present yet. Apply supabase/migrations/0004_pipeline_tester.sql.")
    keep: list[dict] = []
    delete: list[dict] = []
    for row in parts:
        if _is_prince(row) or _is_tester(row):
            keep.append(row)
        else:
            delete.append(row)

    print(f"Live participants: {len(parts)}")
    print("Keep:")
    for row in keep:
        print(f"  - {row.get('display_name')} / {row.get('registration_number')} / {row['id']}")
    print(f"Delete ({len(delete)}):")
    for row in delete:
        print(f"  - {row.get('display_name')} / {row.get('registration_number')} / {row['id']}")

    tester_exists = any(_is_tester(row) for row in parts)

    if not args.apply:
        print("\nDry run. Re-run with --apply to write.")
        return

    for row in delete:
        store.table("pc_participants").delete().eq("id", row["id"]).eq("competition_id", LIVE).execute()
        print(f"deleted {row['id']}")

    if not tester_exists:
        payload = {
            "competition_id": LIVE,
            "registration_id": str(uuid.uuid4()),
            "qr_token": f"{MANUAL_QR_PREFIX}ABHINAV",
            "registration_number": TESTER_REG,
            "display_name": "Pipeline tester",
            "email": None,
            "status": "REGISTERED",
            "is_pipeline_tester": True,
        }
        try:
            created = store.table("pc_participants").insert(payload).execute()
        except Exception:  # noqa: BLE001
            payload.pop("is_pipeline_tester", None)
            created = store.table("pc_participants").insert(payload).execute()
        print(f"seeded tester: {created.data}")
    else:
        tester = next(row for row in parts if _is_tester(row))
        try:
            store.table("pc_participants").update(
                {"is_pipeline_tester": True, "display_name": tester.get("display_name") or "Pipeline tester"}
            ).eq("id", tester["id"]).execute()
        except Exception:  # noqa: BLE001
            store.table("pc_participants").update(
                {"display_name": tester.get("display_name") or "Pipeline tester"}
            ).eq("id", tester["id"]).execute()
        print("marked existing tester")

    prince = [row for row in keep if _is_prince(row)]
    print(f"Prince Agrawal rows remaining: {len(prince)}")
    print("Done. registrations table was not modified.")


if __name__ == "__main__":
    main()
