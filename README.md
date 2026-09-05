# Prompt Writing Competition Platform

Minimal, durable, asynchronous platform for a prompt-writing competition (Master
Prompters 2.0). Participants sign in with their registration number, then confirm
with the event QR code, write five prompts, and submit once. The backend stores
submissions and enqueues async evaluation jobs; it never waits on the LLM in the
request path.

## Stack

- **Frontend** — React + TypeScript + Vite, Tailwind CSS, shadcn/ui + Radix, Motion
- **Backend** — Python + FastAPI + Pydantic
- **Database** — Supabase PostgreSQL (existing schema is reused read-only; new
  `pc_*` tables are additive)
- **LLM** — Google Gemini (evaluator stub until rubric is supplied)

## Repo layout

```
frontend/          React + Vite SPA
backend/           FastAPI service
supabase/
  migrations/       new-table migrations + seed (0000_full_setup.sql = combined)
scripts/
  apply_db.py       optional direct DB apply (needs DATABASE_URL)
  e2e_production_test.py   end-to-end test against the TEST competition
docs/
  SETUP.md          step-by-step setup
```

## Quick start

See [docs/SETUP.md](docs/SETUP.md). The one manual prerequisite is:
paste **`supabase/migrations/0000_full_setup.sql`** into the Supabase SQL editor
and run it (creates the new `pc_*` tables + seeds the competition). Existing
tables are untouched.

Then:

```bash
# backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# frontend (new terminal)
cd frontend
npm install
npm run dev
```

## Authentication

Participants enter their event registration number, then scan or paste the QR
code (`GENAI_QR_...`). The QR is matched against the existing `registrations`
table (read-only). A pipeline tester account can sign in with registration
number only and is excluded from leaderboards.

## Security

- `SUPABASE_SERVICE_ROLE_KEY` and `GEMINI_API_KEY` are server-side only.
- RLS on all new tables; the frontend never sees the service-role key.
- Participant can only read/write their own submission (enforced in backend).
- Admin is a separate username/password login (bcrypt-verified, rate-limited) that
  mints a `role=admin` JWT; admin ops live under `/admin` with a Live / Test mode switch.

## Testing

```bash
cd backend && .venv/Scripts/python.exe -m pytest -q
cd frontend && npm run lint && npm run typecheck

# optional end-to-end checks against a running server (does not wipe the
# authored 1500-prompt TEST dataset unless you pass --wipe-test-data):
cd backend && .venv/Scripts/python.exe ../scripts/e2e_production_test.py --mode admin
```

Populate the isolated TEST competition from CLI only:

```bash
python scripts/populate_test_dataset.py --total 300
```

Admin → Test mode runs the same Gemini evaluation path as live. There is no
dummy evaluator and no seed/cleanup UI.