"""Apply every prompt-competition SQL migration to Supabase.

Two options:
  A) Paste each file in supabase/migrations/ into the Supabase SQL editor
     (recommended — it runs with full privileges).
  B) This script runs them over a direct Postgres connection if DATABASE_URL is
     set (the postgres host + password), e.g.:
         set DATABASE_URL="postgresql://postgres:<pw>@<ref>.supabase.co:5432/postgres"
         python scripts/apply_db.py

Migrations are applied in filename order. Each file is idempotent
(create/alter if not exists). After all files run, PostgREST schema cache is
reloaded.
"""

from __future__ import annotations

import os
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "supabase" / "migrations"


def migration_files() -> list[Path]:
    if not MIGRATIONS_DIR.is_dir():
        raise SystemExit(f"Migrations directory not found: {MIGRATIONS_DIR}")
    files = sorted(p for p in MIGRATIONS_DIR.glob("*.sql") if p.is_file())
    if not files:
        raise SystemExit(f"No .sql files in {MIGRATIONS_DIR}")
    return files


def main() -> None:
    files = migration_files()
    url = os.getenv("DATABASE_URL")
    if not url:
        listed = "\n".join(f"  - {p.name}" for p in files)
        print(
            "DATABASE_URL is not set.\n"
            "Recommended: run these files in order in the Supabase SQL editor:\n"
            f"{listed}\n"
            "See docs/SETUP.md."
        )
        return

    try:
        import psycopg  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "Install psycopg[binary] to use direct DB apply: pip install 'psycopg[binary]'"
        ) from exc

    with psycopg.connect(url) as conn:
        for path in files:
            sql = path.read_text(encoding="utf-8")
            print(f"Applying {path.name} ...")
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
            print(f"  ok {path.name}")
        with conn.cursor() as cur:
            cur.execute("notify pgrst, 'reload schema'")
        conn.commit()
    print("All migrations applied and PostgREST schema cache refreshed.")


if __name__ == "__main__":
    main()
