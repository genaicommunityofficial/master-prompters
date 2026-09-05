-- ============================================================================
-- Prompt Competition Platform - Master Prompters 2.0 (ADDITIVE)
-- These tables are NEW and coexist with the existing events/registrations DB.
-- Existing tables are NOT modified. The registrations table is read only for
-- QR-token login mapping.
-- Idempotent: safe to run more than once.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- pc_competitions : competition-level configuration
-- ---------------------------------------------------------------------------
create table if not exists public.pc_competitions (
  id                 text primary key,
  event_id           uuid,
  name               text not null,
  slug               text not null unique,
  description        text,
  status             text not null default 'DRAFT'
                     check (status in ('DRAFT','OPEN','CLOSED','RESULTS_PUBLISHED','ARCHIVED','TEST')),
  start_at           timestamptz,
  end_at             timestamptz,
  leaderboard_visible boolean not null default false,
  results_visible    boolean not null default false,
  evaluation_version text not null default 'v0.0.0',
  qr_event_id        uuid,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- pc_questions : the five competition categories (data-driven)
-- ---------------------------------------------------------------------------
create table if not exists public.pc_questions (
  id                text primary key,
  competition_id    text not null references public.pc_competitions(id) on delete cascade,
  question_number   int  not null,
  title             text not null,
  description       text,
  input_type        text not null default 'textarea',
  max_length        int  not null default 500,
  min_length        int  not null default 20,
  display_order     int  not null default 0,
  evaluation_config jsonb,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  unique (competition_id, question_number)
);

-- ---------------------------------------------------------------------------
-- pc_participants : participant membership mapped from QR registration
-- ---------------------------------------------------------------------------
create table if not exists public.pc_participants (
  id              uuid primary key default gen_random_uuid(),
  competition_id  text not null references public.pc_competitions(id) on delete cascade,
  registration_id uuid not null,
  qr_token        text not null,
  display_name    text,
  email           text,
  status          text not null default 'REGISTERED'
                  check (status in ('REGISTERED','SUBMITTED','DISQUALIFIED')),
  created_at      timestamptz not null default now(),
  submitted_at    timestamptz,
  updated_at      timestamptz not null default now(),
  unique (competition_id, registration_id),
  unique (competition_id, qr_token)
);

create index if not exists idx_pc_participants_competition on public.pc_participants(competition_id);

-- ---------------------------------------------------------------------------
-- pc_submissions : one per participant per competition
-- ---------------------------------------------------------------------------
create table if not exists public.pc_submissions (
  id             uuid primary key default gen_random_uuid(),
  competition_id text not null references public.pc_competitions(id) on delete cascade,
  participant_id uuid not null references public.pc_participants(id) on delete cascade,
  status         text not null default 'PROCESSING'
                 check (status in ('DRAFT','SUBMITTED','PROCESSING','COMPLETED','FAILED')),
  submitted_at   timestamptz not null default now(),
  completed_at   timestamptz,
  total_score    numeric,
  rank           int,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  unique (competition_id, participant_id)
);

create index if not exists idx_pc_submissions_competition on public.pc_submissions(competition_id);
create index if not exists idx_pc_submissions_status     on public.pc_submissions(status);

-- ---------------------------------------------------------------------------
-- pc_responses : prompt responses per submission
-- ---------------------------------------------------------------------------
create table if not exists public.pc_responses (
  id             uuid primary key default gen_random_uuid(),
  submission_id  uuid not null references public.pc_submissions(id) on delete cascade,
  question_id    text not null references public.pc_questions(id),
  prompt_text    text not null,
  word_count     int,
  token_estimate int,
  created_at     timestamptz not null default now(),
  unique (submission_id, question_id)
);

create index if not exists idx_pc_responses_submission on public.pc_responses(submission_id);
create index if not exists idx_pc_responses_question   on public.pc_responses(question_id);

-- ---------------------------------------------------------------------------
-- pc_evaluation_jobs : internal job tracking
-- ---------------------------------------------------------------------------
create table if not exists public.pc_evaluation_jobs (
  id            uuid primary key default gen_random_uuid(),
  response_id   uuid not null references public.pc_responses(id) on delete cascade,
  status        text not null default 'QUEUED'
                check (status in ('QUEUED','PROCESSING','RETRY','COMPLETED','FAILED')),
  attempt_count int not null default 0,
  provider      text,
  model         text,
  queued_at     timestamptz not null default now(),
  started_at    timestamptz,
  completed_at  timestamptz,
  locked_at     timestamptz,
  last_error    text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create index if not exists idx_pc_jobs_status     on public.pc_evaluation_jobs(status);
create index if not exists idx_pc_jobs_response   on public.pc_evaluation_jobs(response_id);

-- ---------------------------------------------------------------------------
-- pc_evaluations : actual model evaluation results + cost inputs
-- ---------------------------------------------------------------------------
create table if not exists public.pc_evaluations (
  id                  uuid primary key default gen_random_uuid(),
  response_id         uuid not null references public.pc_responses(id) on delete cascade,
  evaluation_job_id   uuid references public.pc_evaluation_jobs(id),
  score               numeric check (score >= 0 and score <= 100),
  criteria_scores     jsonb,
  reasoning_summary   text,
  model               text,
  model_version       text,
  input_tokens        int,
  output_tokens       int,
  thinking_tokens     int,
  latency_ms          int,
  estimated_cost_usd  numeric,
  evaluation_version  text not null default 'v0.0.0',
  created_at          timestamptz not null default now(),
  unique (response_id, evaluation_version)
);

create index if not exists idx_pc_evaluations_response on public.pc_evaluations(response_id);

-- ---------------------------------------------------------------------------
-- pc_admin_audit_logs : sensitive admin action tracking
-- ---------------------------------------------------------------------------
create table if not exists public.pc_admin_audit_logs (
  id           uuid primary key default gen_random_uuid(),
  admin_email  text,
  action       text not null,
  target_type  text,
  target_id    text,
  metadata     jsonb,
  created_at   timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- pc_request_logs : every backend request (drives real-time admin monitor)
-- ---------------------------------------------------------------------------
create table if not exists public.pc_request_logs (
  id             bigint generated by default as identity primary key,
  request_id     text,
  method         text not null,
  path           text not null,
  status         int,
  latency_ms     int,
  participant_id text,
  ip             text,
  created_at     timestamptz not null default now()
);

create index if not exists idx_pc_request_logs_created on public.pc_request_logs(created_at);
create index if not exists idx_pc_request_logs_path    on public.pc_request_logs(path);

-- ---------------------------------------------------------------------------
-- pc_evaluation_cost_lookup : deterministic Gemini pricing
-- ---------------------------------------------------------------------------
create table if not exists public.pc_evaluation_cost_lookup (
  model           text primary key,
  input_price     numeric not null default 0,   -- USD per 1K tokens
  output_price    numeric not null default 0,
  thinking_price  numeric not null default 0,
  note            text,
  updated_at      timestamptz not null default now()
);

insert into public.pc_evaluation_cost_lookup (model, input_price, output_price, thinking_price, note) values
  ('gemini-2.5-flash', 0.0003, 0.0025, 0.0035, 'Approx Gemini 2.5 Flash pricing (USD per 1K tokens)')
on conflict (model) do update set
  input_price = excluded.input_price,
  output_price = excluded.output_price,
  thinking_price = excluded.thinking_price;

-- ============================================================================
-- Seed: Master Prompters 2.0 + the five real categories
-- ============================================================================
insert into public.pc_competitions
  (id, event_id, name, slug, description, status, evaluation_version, qr_event_id,
   leaderboard_visible, results_visible)
values (
  'competition_2026',
  (select id from public.events where slug = 'master-prompters-2-0' limit 1),
  'Master Prompters 2.0',
  'master-prompters-2-0',
  'Write one original prompt in each of the five categories. Each prompt is judged independently. Submit once.',
  'OPEN',
  'v0.0.0',
  (select id from public.events where slug = 'master-prompters-2-0' limit 1),
  false,
  false
)
on conflict (id) do update set
  name = excluded.name,
  description = excluded.description,
  qr_event_id = excluded.qr_event_id;

-- TEST competition used by the test suite (cleaned after the run).
insert into public.pc_competitions
  (id, name, slug, description, status, leaderboard_visible, results_visible)
values (
  'competition_test',
  'TEST Competition',
  'test-competition',
  'Isolated competition for the test suite. Writes are cleaned automatically.',
  'TEST',
  false,
  false
)
on conflict (id) do nothing;

-- The five categories.
insert into public.pc_questions (id, competition_id, question_number, title, description, input_type, max_length, min_length, display_order, evaluation_config) values
  ('q1', 'competition_2026', 1, 'Meme Generation',
    'Write a prompt that would produce an original, shareable meme. Name the joke, the visual setup or template, the on-screen text, the tone, and the audience. It should read instantly on a phone and stay funny on a second look.', 'textarea', 500, 20, 1, '{}'::jsonb),
  ('q2', 'competition_2026', 2, 'AI Visual Art Creation',
    'Direct an image model as if you were briefing an illustrator. Specify subject, composition, lighting, palette, medium, and mood in enough detail that two people would picture the same artwork.', 'textarea', 500, 20, 2, '{}'::jsonb),
  ('q3', 'competition_2026', 3, 'AI Digital Storytelling / Creative Writing',
    'Write a prompt for a short story or scene. Include character, setting, conflict, narrative voice, and how it should end. Name the genre, approximate length, and any language or point-of-view constraints.', 'textarea', 500, 20, 3, '{}'::jsonb),
  ('q4', 'competition_2026', 4, 'AI Song Factory',
    'Write a prompt for an original song. Specify genre, mood or tempo, song structure (verse, chorus, bridge), vocal character, and the feeling the track should leave. Include a line of lyric direction if it helps.', 'textarea', 500, 20, 4, '{}'::jsonb),
  ('q5', 'competition_2026', 5, 'AI-Generated Poetry in Local Languages',
    'Write a prompt for a poem in an Indian or regional language you name clearly. Specify the form (free verse, ghazal, haiku, and so on), the central images, and what the poem should mean.', 'textarea', 500, 20, 5, '{}'::jsonb),
  ('tq1', 'competition_test', 1, 'Prompt 1', 'Test category one.', 'textarea', 500, 20, 1, '{}'::jsonb),
  ('tq2', 'competition_test', 2, 'Prompt 2', 'Test category two.', 'textarea', 500, 20, 2, '{}'::jsonb),
  ('tq3', 'competition_test', 3, 'Prompt 3', 'Test category three.', 'textarea', 500, 20, 3, '{}'::jsonb),
  ('tq4', 'competition_test', 4, 'Prompt 4', 'Test category four.', 'textarea', 500, 20, 4, '{}'::jsonb),
  ('tq5', 'competition_test', 5, 'Prompt 5', 'Test category five.', 'textarea', 500, 20, 5, '{}'::jsonb)
on conflict (id) do update set
  title = excluded.title,
  description = excluded.description,
  max_length = excluded.max_length,
  min_length = excluded.min_length;

-- ============================================================================
-- Row Level Security
-- ============================================================================
alter table public.pc_competitions enable row level security;
alter table public.pc_questions     enable row level security;
alter table public.pc_participants  enable row level security;
alter table public.pc_submissions   enable row level security;
alter table public.pc_responses     enable row level security;
alter table public.pc_evaluation_jobs enable row level security;
alter table public.pc_evaluations   enable row level security;
alter table public.pc_admin_audit_logs enable row level security;
alter table public.pc_request_logs  enable row level security;
alter table public.pc_evaluation_cost_lookup enable row level security;

create policy "pc_competitions_public_read" on public.pc_competitions
  for select using (true);

create policy "pc_questions_public_read" on public.pc_questions
  for select using (true);

create policy "pc_cost_lookup_public_read" on public.pc_evaluation_cost_lookup
  for select using (true);

-- Participants may read their own rows.
create policy "pc_participants_own_read" on public.pc_participants
  for select using (auth.uid() is not null);
create policy "pc_submissions_own_read" on public.pc_submissions
  for select using (auth.uid() is not null);
create policy "pc_responses_own_read" on public.pc_responses
  for select using (auth.uid() is not null);

-- Internal tables: no public read (admin via service role only)
revoke all on table public.pc_evaluation_jobs from anon, authenticated;
revoke all on table public.pc_evaluations     from anon, authenticated;
revoke all on table public.pc_admin_audit_logs from anon, authenticated;
revoke all on table public.pc_request_logs    from anon, authenticated;

grant select on public.pc_competitions to anon, authenticated;
grant select on public.pc_questions     to anon, authenticated;
grant select on public.pc_evaluation_cost_lookup to anon, authenticated;