"""Apply the prompt-competition SQL migrations to Supabase.

Two options:
  A) The user pastes supabase/migrations/0000_full_setup.sql into the Supabase
     SQL editor (recommended — it runs with full privileges).
  B) This script runs it over a direct Postgres connection if DATABASE_URL is
     set (the postgres host + password), e.g.:
         set DATABASE_URL="postgresql://postgres:<pw>@<ref>.supabase.co:5432/postgres"
         python scripts/apply_db.py
"""

from __future__ import annotations

import os
from pathlib import Path

SQL_FILE = Path(__file__).resolve().parents[1] / "supabase" / "migrations" / "0000_full_setup.sql"


def main() -> None:
    if not SQL_FILE.exists():
        raise SystemExit(f"Migration file not found: {SQL_FILE}")

    url = os.getenv("DATABASE_URL")
    if not url:
        print(
            "DATABASE_URL is not set.\n"
            "Recommended: open supabase/migrations/0000_full_setup.sql in the "
            "Supabase SQL editor and run it. See docs/SETUP.md."
        )
        return

    try:
        import psycopg  # type: ignore
    except ImportError as exc:
        raise SystemExit("Install psycopg[binary] to use direct DB apply: " "pip install 'psycopg[binary]'") from exc

    sql = SQL_FILE.read_text(encoding="utf-8")
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        # Refresh PostgREST schema cache.
        with conn.cursor() as cur:
            cur.execute("notify pgrst, 'reload schema'")
        conn.commit()
    print("Migration applied and PostgREST schema cache refreshed.")


if __name__ == "__main__":
    main()