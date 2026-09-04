# Prompt Writing Competition Platform

Minimal, durable, asynchronous platform for a prompt-writing competition (Master
Prompters 2.0). Participants sign in with their registration QR code, write five
prompts, and submit once. The backend stores submissions and enqueues async
evaluation jobs; it never waits on the LLM in the request path.

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
  stress_test.py    auto-cleaning load test (no LLM)
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

## Authentication (QR login)

Participants already have a QR code from the existing registration site. The QR
message (e.g. `GENAI_QR_...`) is decoded from an uploaded image with OpenCV, or
pasted as text, then matched against the existing `registrations.qr_token` to
map identity — no new credentials required.

## Security

- `SUPABASE_SERVICE_ROLE_KEY` and `GEMINI_API_KEY` are server-side only.
- RLS on all new tables; the frontend never sees the service-role key.
- Participant can only read/write their own submission (enforced in backend).
- Admin is a separate username/password login (bcrypt-verified, rate-limited) that
  mints a `role=admin` JWT; admin ops (dashboard, live monitor, cost analytics,
  prompt export, stress-test cleanup) are exposed via `frontend/src/pages/admin.tsx`.

## Testing

```bash
cd backend && .venv/Scripts/python.exe -m pytest -q   # 12 tests
cd frontend && npm run lint && npm run typecheck

# optional auto-cleaning load test (against the TEST competition, no LLM):
cd backend && .venv/Scripts/python.exe ../scripts/stress_test.py --total 200
```