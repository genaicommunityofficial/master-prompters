"""This script used to insert into the shared registrations table.

That is no longer allowed. Pipeline testing uses pc_participants only:
  python scripts/cleanup_live_participants.py --apply
"""
from __future__ import annotations

import sys


def main() -> None:
    raise SystemExit(
        "Do not write to the registrations table.\n"
        "Use scripts/cleanup_live_participants.py --apply to seed "
        "abhinavkumarsaksena on pc_participants, or add a number from the admin Participants page."
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
