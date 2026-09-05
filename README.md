# Prompt Writing Competition Platform

Minimal, durable platform for Master Prompters 2.0. Participants sign in with
their registration number, confirm with the event QR code, write five prompts,
and submit once. Evaluation is started later from a local admin app; the
participant request path never waits on the LLM.

## How it is deployed

- **Participants** — React SPA on **Vercel**, talking **directly** to **Supabase**
  with the anon key (login, submit, public leaderboard). No FastAPI in this path.
- **Admin + Gemini eval** — FastAPI on **your laptop**, using the service-role
  key. Open/close the competition, run evaluation for hours, publish results.
- After publish, participants reload `/leaderboard` on Vercel.

Never put `SUPABASE_SERVICE_ROLE_KEY` or `GEMINI_API_KEY` in the frontend or on
Vercel.

## Stack

- **Frontend** — React + TypeScript + Vite, Tailwind CSS, shadcn/ui + Radix, Motion
- **Backend** — Python + FastAPI + Pydantic (admin + evaluator, local)
- **Database** — Supabase PostgreSQL (existing schema is reused read-only; new
  `pc_*` tables are additive)
- **LLM** — Google Gemini (evaluator; run from the laptop)

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

See [docs/SETUP.md](docs/SETUP.md). Paste **`supabase/migrations/`** in order
(`0000` … `0007`) into the Supabase SQL editor. Existing tables are untouched.
`0005` + `0007` are required before the Vercel participant site can log in or submit.

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

- `SUPABASE_SERVICE_ROLE_KEY` and `GEMINI_API_KEY` are laptop/backend only.
- RLS on all new tables; the Vercel app only has the anon key and SECURITY
  DEFINER RPCs (`pc_login_*`, `pc_submit*`, `pc_public_leaderboard`).
- Admin is a separate username/password login (bcrypt-verified, rate-limited) that
  mints a `role=admin` JWT; use `/admin` on localhost with a Live / Test mode switch.

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