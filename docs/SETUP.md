# Prompt Competition Platform — Setup

## Prerequisites

- **Supabase project** (currently `yvvjfvdpbhktmsqfordh`) — the existing `events`,
  `registrations`, and `checkins` tables belong to it and are read-only for this app.
- **Google Gemini API key** (optional now; used by the evaluator later).
- Python 3.12+ and Node 18+.

## 1. Create the database tables (ONE TIME)

The app needs new tables that **do not modify** the existing schema. Apply every
file in **`supabase/migrations/`** in order (`0000` … `0011`) by pasting into the
Supabase **SQL Editor**, or run `python scripts/apply_db.py` when `DATABASE_URL`
is set.

`0000_full_setup.sql` creates:

```
pc_competitions   competition configuration
pc_questions      the five categories (data-driven)
pc_participants   mapped from QR registrations
pc_submissions    one per participant
pc_responses      five per submission
pc_evaluation_jobs  internal job queue
pc_evaluations    model evaluation results + scores
pc_admin_audit_logs sensitive admin actions
pc_request_logs   durable per-request logs (real-time admin monitor)
pc_evaluation_cost_lookup  deterministic Gemini pricing
```

Later additive migrations:

- `0001_eval_criteria.sql` — `pc_eval_criteria` (markdown rubrics)
- `0002_registration_number.sql` — `pc_participants.registration_number`
- `0003_participant_login_tracking.sql` — `login_count` / `last_login_at`
- `0004_pipeline_tester.sql` — `pc_participants.is_pipeline_tester`
- `0005_participant_supabase_rpcs.sql` — anon RPCs for login, submit, public leaderboard
- `0006_pgcrypto_search_path.sql` — include `extensions` on RPC search_path
- `0007_session_token_no_pgcrypto.sql` — mint login tokens without `gen_random_bytes` (required after 0005)
- `0008_eval_cost_gemini_36.sql` — seed `gemini-3.6-flash` prices in `pc_evaluation_cost_lookup`
- `0009_prompt_length_500.sql` — live and TEST questions: 20–500 characters, richer category descriptions
- `0010_prompt_length_2000.sql` — raise max length to 2000 characters (min stays 20)
- `0011_session_lock_frozen_prompts.sql` — one active login per registration; saved prompts cannot be overwritten

It also seeds the **Master Prompters 2.0** competition with the **five real
categories**, plus an isolated **TEST** competition used by the test suite:

1. Meme Generation
2. AI Visual Art Creation
3. AI Digital Storytelling / Creative Writing
4. AI Song Factory
5. AI-Generated Poetry in Local Languages

Each prompt must be **20–2000 characters**. Apply `0010` on existing projects so
the form, submit RPCs, and Gemini eval all see the new limits.

> The evaluation rubric is intentionally left empty. It will be supplied later as
> a versioned configuration, not hardcoded.

If you applied an earlier draft migration (before `pc_request_logs` and the real
category titles), just re-run `0000_full_setup.sql` — it is idempotent and additive.

## 2. Backend configuration

```
cd backend
copy .env.example .env   # then edit .env
```

| Variable | Value |
|---|---|
| `SUPABASE_URL` | your project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | service-role key (server only) |
| `SUPABASE_ANON_KEY` | anon key (used for auth) |
| `GEMINI_API_KEY` | leave empty until rubric provided |
| `QR_EVENT_ID` | existing event id whose registrations are accepted |
| `JWT_SECRET` | change to a long random value |
| `ADMIN_USERNAME` | admin login username (default `admin`) |
| `ADMIN_PASSWORD_HASH` | bcrypt hash of the admin password; if empty, admin login is disabled |
| `ADMIN_CODES` | comma-separated admin emails (legacy) |
| `LOG_LEVEL` / `REQUEST_LOG_ENABLED` | logging/monitor toggles |

Create the admin password hash with:

```
python -c "import bcrypt;print(bcrypt.hashpw(b'<password>',bcrypt.gensalt(12)).decode())"
```

Run:

```
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend runs at `http://localhost:8000`.

## 3. Frontend configuration

```
cd frontend
copy .env.example .env.local
```

Fill **only** the public Supabase values (Project Settings → API):

| Variable | Value |
|---|---|
| `VITE_SUPABASE_URL` | `https://<project>.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | the **anon** `public` key — never the service-role key |
| `VITE_API_BASE_URL` | leave empty |

Empty `VITE_API_BASE_URL` is correct:

- **Vite dev** still proxies `/api` to FastAPI for the admin control room.
- **Vercel** participants talk to Supabase directly; they never call FastAPI.

```
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`. Participant login/submit uses the
Supabase RPCs from migration `0005`. Admin pages still use FastAPI on
`http://localhost:8000`.

## 4. Authentication flow

1. Participant signs in with their **registration number**, then confirms with
   the event QR (upload or paste `GENAI_QR_...`). Pipeline testers and
   admin-added numbers skip the QR step.
2. The browser calls Supabase RPCs (`pc_login_registration`, `pc_login_qr`).
   Those functions read **`registrations` read-only**, create/reuse a
   `pc_participants` row, and return a hashed session token (not a JWT).
3. The frontend stores that token locally and uses it for submit.
4. The participant answers the five questions and submits once. Submit writes
   `pc_submissions` + `pc_responses` only — evaluation is started later from
   the local admin app.

## 5. Evaluation pipeline

Submission never waits on the LLM:

```
POST /api/submissions
   ↓
validate + create submission + responses + QUEUED evaluation jobs
   ↓
return success immediately
```

An evaluator worker consumes QUEUED jobs. In this first delivery the evaluator is
a logged stub (`LogOnlyEvaluator`) until the rubric is supplied. Admin can drain
the queue via **Admin → Process queue**, which calls
`POST /api/admin/evaluations/process-queue`.

## 6. Seeding / testing

- `GET /api/competitions/active` returns the open competition.
- `GET /api/competitions/{id}` returns the competition + its five questions.
- `POST /api/auth/login/message` with `{ competition_id, qr_message }` returns a token.

## 7. Admin access

Sign in at **Admin** (link in the site header nav → `/admin`) with the username +
password from `ADMIN_USERNAME` / `ADMIN_PASSWORD_HASH`. The backend verifies the
bcrypt password (rate-limited per IP), issues a `role=admin` JWT, and the frontend
stores it separately from the participant session.

> The admin **plaintext password is never stored**. It is set once and only its
> bcrypt hash lives in `backend/.env` (`ADMIN_PASSWORD_HASH`). Rotate it before
> production. To log in programmatically (e.g. the E2E harness), pass the plaintext
> via the `ADMIN_PASSWORD` environment variable — it is read only by the harness,
> never committed.

Admin capabilities:

- **Dashboard** (`/admin`) — open/close submissions, start Gemini eval, publish leaderboard.
- **Participants** (`/admin/participants`) — event registrations (read-only) plus
  admin-added numbers, with login status on live.
- **Evaluation** (`/admin/eval`) — pipeline, cost, logs, request monitor.
- **Criteria / Export** — rubrics and CSV, scoped by Live / Test mode.

A **Test mode** switch in the admin header scopes every page to `competition_test`
(the authored ~1500-prompt dataset). Public participants always stay on live.

Endpoints: `POST /api/admin/login`, `GET /api/admin/dashboard?competition_id=`,
`GET /api/admin/eval-status?competition_id=`, `POST /api/admin/evaluations/start`,
`GET /api/admin/evaluations/logs`, `GET /api/admin/leaderboard?competition_id=`,
`GET /api/admin/participants`, `GET /api/admin/monitor/live`,
`GET /api/admin/monitor/logs`, `GET /api/admin/analytics`,
`GET /api/admin/export/csv?category=N`, `GET|POST /api/admin/criteria`,
`POST /api/admin/criteria/copy-live`, `POST /api/admin/registrations`.

## 8. Test pipeline (isolated TEST competition)

The **Test mode** switch in the admin header evaluates the authored dataset already
in `competition_test` (300 participants × 5 categories = 1500 prompts). Populate
or replace that dataset from CLI only:

```
python scripts/populate_test_dataset.py --total 300
```

Start evaluation from Evaluation while Test mode is on — it calls the same Gemini
path as live. Watch progress, cost, failures, and the test leaderboard there. Do
not wipe this dataset from the UI.

### 8b. End-to-end production test (PASS/FAIL)

`scripts/e2e_production_test.py` exercises real flows against Supabase and exits
`0` (PASS) or `1` (FAIL). It never mutates live `competition_2026` submissions.
By default it **does not delete** the TEST dataset. Pass
`--wipe-test-data` only when you intentionally want to clear `competition_test`.

Modes:

- `smoke` — active competition load, real QR-login mapping, unauthenticated-401,
  one synthetic TEST submission, 5-responses assertion.
- `admin` — login, dashboard, monitor, analytics, export, eval-status (live + test),
  participation, admin leaderboard.
- `eval` — assert TEST eval-status shape and that `POST /evaluations/start` for
  `competition_test` uses the real Gemini path (does not seed or wipe).
- `seed` — CLI seed N TEST participants (does not run unless you pick this mode).
- `all` — smoke, then admin, then eval (does not seed or wipe).

Against an already-running backend:

```
$env:ADMIN_PASSWORD="<the admin plaintext password>"
python scripts/e2e_production_test.py --base-url http://127.0.0.1:8117 --mode all
```

Or against production (needs the admin password scope + network access):

```
python scripts/e2e_production_test.py --base-url https://<host>/api --mode all
```

The runner reads `backend/.env` for Supabase creds and `JWT_SECRET`, mints local
participant JWTs, and requires `ADMIN_PASSWORD` only for the `admin` mode.

## 9. Deployment (Vercel participants + laptop eval)

This is the intended production shape for ~300 concurrent participants:

```
Participants  →  Vercel (static SPA)  →  Supabase (anon key + RPCs)
You           →  local Vite + FastAPI →  Supabase (service role) → Gemini
Publish       →  FastAPI sets leaderboard_visible
Participants  →  reload /leaderboard  →  pc_public_leaderboard RPC
```

### Vercel (frontend only)

1. New Vite project, **Root Directory** = `frontend`.
2. Build: `npm run build`. Output: `dist`.
3. Environment variables (Production + Preview):

   - `VITE_SUPABASE_URL`
   - `VITE_SUPABASE_ANON_KEY`

   Do **not** set `VITE_API_BASE_URL`. Do **not** add `SUPABASE_SERVICE_ROLE_KEY`
   or `GEMINI_API_KEY` to Vercel.

4. Apply `0005` then `0007` in the SQL editor before the first login
   (`0006` is optional if `0007` is applied).

A Vercel HTTPS page cannot call `http://127.0.0.1:8000` (mixed content). Admin
on the deployed site shows a “run on your laptop” message on purpose.

### Laptop (admin + Gemini)

Keep using local frontend + backend:

```
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

cd frontend
npm run dev
```

Open `http://localhost:5173/admin`. Open the live competition, start Gemini eval
(concurrency **2** on 8 GB RAM), then **Publish leaderboard**. Participants on
Vercel reload and see ranks. Leave other heavy apps closed during a long eval run.