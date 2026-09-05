-- ============================================================================
-- Master Prompters 2.0: participant path via Supabase (Vercel + anon key)
-- ADDITIVE. Does not modify registrations / events / checkins.
--
-- The public SPA talks to Postgres through SECURITY DEFINER RPCs granted to
-- `anon`. Tables stay locked down by RLS (no direct insert/update for anon).
-- FastAPI (run locally) keeps using the service role for admin + Gemini eval.
--
-- Apply after 0003 and 0004. Idempotent. Ends with a PostgREST schema reload.
-- ============================================================================

-- Session tokens use gen_random_uuid() (pg_catalog), not pgcrypto.gen_random_bytes,
-- because hosted DBs often keep pgcrypto off the SECURITY DEFINER search_path.
create extension if not exists pgcrypto;

alter table public.pc_participants
  add column if not exists login_count int not null default 0;

alter table public.pc_participants
  add column if not exists last_login_at timestamptz;

alter table public.pc_participants
  add column if not exists is_pipeline_tester boolean not null default false;

alter table public.pc_participants
  add column if not exists session_token_hash text;

create unique index if not exists uq_pc_participants_session_hash
  on public.pc_participants (session_token_hash)
  where session_token_hash is not null;

-- ---------------------------------------------------------------------------
-- Internal helpers (revoke PUBLIC execute below)
-- ---------------------------------------------------------------------------

create or replace function public._pc_norm_reg(p_value text)
returns text
language sql
immutable
as $$
  select trim(coalesce(p_value, ''));
$$;

create or replace function public._pc_norm_qr(p_message text)
returns text
language plpgsql
immutable
as $$
declare
  v_msg text := trim(coalesce(p_message, ''));
  v_idx int;
  v_rest text;
  v_match text;
begin
  v_idx := position('GENAI_QR_' in v_msg);
  if v_idx > 0 then
    v_rest := substr(v_msg, v_idx);
    v_match := (regexp_match(v_rest, '^[A-Za-z0-9_]+'))[1];
    if v_match is not null then
      return v_match;
    end if;
  end if;
  return v_msg;
end;
$$;

create or replace function public._pc_hash_session(p_token text)
returns text
language sql
immutable
set search_path = public, pg_catalog
as $$
  select md5(p_token) || md5('pc-session|' || p_token);
$$;

create or replace function public._pc_word_count(p_text text)
returns int
language sql
immutable
as $$
  select coalesce((
    select count(*)::int
    from regexp_split_to_table(trim(coalesce(p_text, '')), '\s+') as w
    where w ~ '[[:alnum:]]'
  ), 0);
$$;

create or replace function public._pc_can_skip_qr(p_participant public.pc_participants)
returns boolean
language plpgsql
stable
as $$
begin
  if coalesce(p_participant.is_pipeline_tester, false) then
    return true;
  end if;
  if lower(public._pc_norm_reg(p_participant.registration_number)) = 'abhinavkumarsaksena' then
    return true;
  end if;
  return coalesce(p_participant.qr_token, '') like 'GENAI_QR_MANUAL_%';
end;
$$;

create or replace function public._pc_issue_session(
  p_participant public.pc_participants,
  p_competition_id text,
  p_registration_number text
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  v_token text;
  v_already boolean;
begin
  v_token := 'pcs_' || replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '');

  update public.pc_participants
  set
    session_token_hash = public._pc_hash_session(v_token),
    login_count = coalesce(login_count, 0) + 1,
    last_login_at = now(),
    updated_at = now()
  where id = p_participant.id;

  select exists (
    select 1
    from public.pc_submissions s
    where s.participant_id = p_participant.id
      and s.competition_id = p_competition_id
  ) into v_already;

  return jsonb_build_object(
    'requires_qr', false,
    'token', v_token,
    'participant', jsonb_build_object(
      'competition_id', p_competition_id,
      'participant_id', p_participant.id,
      'display_name', coalesce(p_participant.display_name, 'Participant'),
      'email', p_participant.email,
      'vit_registration_number', coalesce(
        nullif(public._pc_norm_reg(p_registration_number), ''),
        p_participant.registration_number
      ),
      'already_submitted', v_already
    ),
    'display_name', coalesce(p_participant.display_name, 'Participant')
  );
end;
$$;

create or replace function public._pc_participant_from_session(p_session_token text)
returns public.pc_participants
language plpgsql
stable
security definer
set search_path = public, extensions
as $$
declare
  v_row public.pc_participants;
  v_hash text;
begin
  if public._pc_norm_reg(p_session_token) = '' then
    raise exception 'Please sign in again.' using errcode = '28000';
  end if;
  v_hash := public._pc_hash_session(p_session_token);
  select * into v_row
  from public.pc_participants
  where session_token_hash = v_hash
  limit 1;
  if not found then
    raise exception 'Please sign in again.' using errcode = '28000';
  end if;
  return v_row;
end;
$$;

create or replace function public._pc_ensure_participant_from_reg(
  p_competition_id text,
  p_reg public.registrations
)
returns public.pc_participants
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_row public.pc_participants;
  v_number text;
  v_name text;
  v_email text;
begin
  select * into v_row
  from public.pc_participants
  where competition_id = p_competition_id
    and qr_token = p_reg.qr_token
  limit 1;
  if found then
    v_number := public._pc_norm_reg(p_reg.vit_registration_number);
    if v_number <> '' and public._pc_norm_reg(v_row.registration_number) = '' then
      update public.pc_participants
      set registration_number = v_number, updated_at = now()
      where id = v_row.id;
      v_row.registration_number := v_number;
    end if;
    return v_row;
  end if;

  v_number := nullif(public._pc_norm_reg(p_reg.vit_registration_number), '');
  v_name := nullif(trim(coalesce(p_reg.full_name, '')), '');
  v_email := coalesce(p_reg.personal_email, p_reg.college_email);

  insert into public.pc_participants (
    competition_id,
    registration_id,
    qr_token,
    display_name,
    email,
    status,
    is_pipeline_tester,
    registration_number
  ) values (
    p_competition_id,
    p_reg.id,
    p_reg.qr_token,
    v_name,
    v_email,
    'REGISTERED',
    false,
    v_number
  )
  on conflict (competition_id, qr_token) do update
    set display_name = coalesce(excluded.display_name, public.pc_participants.display_name),
        updated_at = now()
  returning * into v_row;

  return v_row;
end;
$$;

-- ---------------------------------------------------------------------------
-- Public RPCs (anon)
-- ---------------------------------------------------------------------------

create or replace function public.pc_login_registration(
  p_competition_id text,
  p_registration_number text
)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_comp public.pc_competitions;
  v_needle text;
  v_participant public.pc_participants;
  v_reg public.registrations;
  v_event text;
begin
  v_needle := public._pc_norm_reg(p_registration_number);
  if v_needle = '' then
    raise exception 'Please enter your registration number.';
  end if;

  select * into v_comp
  from public.pc_competitions
  where id = p_competition_id
  limit 1;
  if not found then
    raise exception 'Competition not found';
  end if;
  if v_comp.status not in ('OPEN', 'RESULTS_PUBLISHED') then
    raise exception 'Competition is not accepting logins right now';
  end if;

  select * into v_participant
  from public.pc_participants
  where competition_id = p_competition_id
    and lower(public._pc_norm_reg(registration_number)) = lower(v_needle)
  limit 1;

  if found and public._pc_can_skip_qr(v_participant) then
    return public._pc_issue_session(
      v_participant,
      p_competition_id,
      coalesce(v_participant.registration_number, v_needle)
    );
  end if;

  if found then
    return jsonb_build_object(
      'requires_qr', true,
      'token', null,
      'participant', null,
      'display_name', v_participant.display_name
    );
  end if;

  v_event := coalesce(v_comp.qr_event_id::text, '');

  select * into v_reg
  from public.registrations r
  where lower(public._pc_norm_reg(r.vit_registration_number)) = lower(v_needle)
    and (v_event = '' or r.event_id::text = v_event)
  limit 1;

  if not found then
    raise exception 'This registration number is not registered for this event.';
  end if;

  return jsonb_build_object(
    'requires_qr', true,
    'token', null,
    'participant', null,
    'display_name', nullif(trim(coalesce(v_reg.full_name, '')), '')
  );
end;
$$;

create or replace function public.pc_login_qr(
  p_competition_id text,
  p_registration_number text,
  p_qr_message text
)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_comp public.pc_competitions;
  v_expected text;
  v_qr text;
  v_reg public.registrations;
  v_actual text;
  v_event text;
  v_status text;
  v_participant public.pc_participants;
  v_session jsonb;
begin
  v_expected := public._pc_norm_reg(p_registration_number);
  if v_expected = '' then
    raise exception 'Enter your registration number first, then scan your QR code.';
  end if;

  select * into v_comp
  from public.pc_competitions
  where id = p_competition_id
  limit 1;
  if not found then
    raise exception 'Competition not found';
  end if;
  if v_comp.status not in ('OPEN', 'RESULTS_PUBLISHED') then
    raise exception 'Competition is not accepting logins right now';
  end if;

  v_qr := public._pc_norm_qr(p_qr_message);
  select * into v_reg
  from public.registrations
  where qr_token = v_qr
  limit 1;
  if not found then
    raise exception 'That QR code is not recognised. Please check your QR code and try again.';
  end if;

  v_event := coalesce(v_comp.qr_event_id::text, '');
  if v_event <> '' and v_reg.event_id::text is distinct from v_event then
    raise exception 'QR code is not registered for this event';
  end if;

  v_status := lower(coalesce(v_reg.registration_status, ''));
  if v_status not in ('verified', 'confirmed', 'approved') then
    raise exception 'Registration is not verified yet';
  end if;

  v_actual := public._pc_norm_reg(v_reg.vit_registration_number);
  if lower(v_actual) is distinct from lower(v_expected) then
    raise exception 'That QR code does not match the registration number you entered.';
  end if;

  v_participant := public._pc_ensure_participant_from_reg(p_competition_id, v_reg);
  v_session := public._pc_issue_session(
    v_participant,
    p_competition_id,
    coalesce(nullif(v_actual, ''), v_expected)
  );
  return jsonb_build_object(
    'token', v_session ->> 'token',
    'participant', v_session -> 'participant'
  );
end;
$$;

create or replace function public.pc_submission_exists(p_session_token text)
returns jsonb
language plpgsql
stable
security definer
set search_path = public, extensions
as $$
declare
  v_p public.pc_participants;
begin
  v_p := public._pc_participant_from_session(p_session_token);
  return jsonb_build_object(
    'submitted', exists (
      select 1
      from public.pc_submissions s
      where s.participant_id = v_p.id
        and s.competition_id = v_p.competition_id
    )
  );
end;
$$;

create or replace function public.pc_submit(
  p_session_token text,
  p_competition_id text,
  p_prompts jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_p public.pc_participants;
  v_comp public.pc_competitions;
  v_sub public.pc_submissions;
  v_prompt jsonb;
  v_qid text;
  v_text text;
  v_q public.pc_questions;
  v_count int;
  v_resp_count int;
  v_msg text := 'Your responses have been saved. Evaluation starts when an administrator runs it.';
begin
  v_p := public._pc_participant_from_session(p_session_token);
  if v_p.competition_id is distinct from p_competition_id then
    raise exception 'Competition mismatch.';
  end if;

  select * into v_comp from public.pc_competitions where id = p_competition_id;
  if not found then
    raise exception 'Competition not found.';
  end if;
  if v_comp.status not in ('OPEN', 'TEST') then
    raise exception 'Competition is not currently accepting submissions.';
  end if;

  v_count := jsonb_array_length(coalesce(p_prompts, '[]'::jsonb));
  if v_count <> 5 then
    raise exception 'Exactly five responses are required.';
  end if;

  perform 1 from public.pc_participants where id = v_p.id for update;

  select * into v_sub
  from public.pc_submissions
  where participant_id = v_p.id
    and competition_id = p_competition_id
  for update;

  if found and v_sub.status in ('SUBMITTED', 'COMPLETED') then
    return jsonb_build_object(
      'submission_id', v_sub.id,
      'status', v_sub.status,
      'message', 'Your responses have been successfully submitted.'
    );
  end if;

  if not found then
    insert into public.pc_submissions (competition_id, participant_id, status, submitted_at)
    values (p_competition_id, v_p.id, 'SUBMITTED', now())
    returning * into v_sub;
  end if;

  for v_prompt in select value from jsonb_array_elements(p_prompts)
  loop
    v_qid := v_prompt ->> 'question_id';
    v_text := trim(coalesce(v_prompt ->> 'prompt_text', ''));
    select * into v_q
    from public.pc_questions
    where id = v_qid
      and competition_id = p_competition_id;
    if not found then
      raise exception 'One of the questions is not valid for this competition.';
    end if;
    if length(v_text) < coalesce(v_q.min_length, 0) then
      raise exception '%', format('%s must be at least %s characters.', v_q.title, v_q.min_length);
    end if;
    if length(v_text) > coalesce(v_q.max_length, 2000) then
      raise exception '%', format('%s must be at most %s characters long.', v_q.title, v_q.max_length);
    end if;

    insert into public.pc_responses (
      submission_id, question_id, prompt_text, word_count, token_estimate
    ) values (
      v_sub.id,
      v_qid,
      v_text,
      public._pc_word_count(v_text),
      greatest(1, length(v_text) / 4)
    )
    on conflict (submission_id, question_id) do update
      set prompt_text = excluded.prompt_text,
          word_count = excluded.word_count,
          token_estimate = excluded.token_estimate;
  end loop;

  select count(*) into v_resp_count from public.pc_responses where submission_id = v_sub.id;
  if v_resp_count >= 5 then
    update public.pc_submissions
    set status = 'SUBMITTED', submitted_at = now(), updated_at = now()
    where id = v_sub.id;
    update public.pc_participants
    set status = 'SUBMITTED', submitted_at = now(), updated_at = now()
    where id = v_p.id;
    v_sub.status := 'SUBMITTED';
  end if;

  return jsonb_build_object(
    'submission_id', v_sub.id,
    'status', coalesce(v_sub.status, 'SUBMITTED'),
    'message', v_msg
  );
end;
$$;

create or replace function public.pc_submit_one(
  p_session_token text,
  p_competition_id text,
  p_question_id text,
  p_prompt_text text
)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_p public.pc_participants;
  v_comp public.pc_competitions;
  v_q public.pc_questions;
  v_sub public.pc_submissions;
  v_text text;
  v_resp_count int;
  v_remaining int;
begin
  v_p := public._pc_participant_from_session(p_session_token);
  if v_p.competition_id is distinct from p_competition_id then
    raise exception 'Competition mismatch.';
  end if;

  select * into v_comp from public.pc_competitions where id = p_competition_id;
  if not found then
    raise exception 'Competition not found.';
  end if;
  if v_comp.status not in ('OPEN', 'TEST') then
    raise exception 'Competition is not currently accepting submissions.';
  end if;

  select * into v_q
  from public.pc_questions
  where id = p_question_id
    and competition_id = p_competition_id;
  if not found then
    raise exception 'That question is not valid for this competition.';
  end if;

  v_text := trim(coalesce(p_prompt_text, ''));
  if length(v_text) < coalesce(v_q.min_length, 0) then
    raise exception '%', format('%s must be at least %s characters.', v_q.title, v_q.min_length);
  end if;
  if length(v_text) > coalesce(v_q.max_length, 2000) then
    raise exception '%', format('%s must be at most %s characters long.', v_q.title, v_q.max_length);
  end if;

  perform 1 from public.pc_participants where id = v_p.id for update;

  select * into v_sub
  from public.pc_submissions
  where participant_id = v_p.id
    and competition_id = p_competition_id
  for update;

  if found and v_sub.status in ('SUBMITTED', 'COMPLETED') then
    return jsonb_build_object(
      'submission_id', v_sub.id,
      'status', v_sub.status,
      'message', 'Your responses have been successfully submitted.'
    );
  end if;

  if not found then
    insert into public.pc_submissions (competition_id, participant_id, status, submitted_at)
    values (p_competition_id, v_p.id, 'PROCESSING', now())
    returning * into v_sub;
  end if;

  insert into public.pc_responses (
    submission_id, question_id, prompt_text, word_count, token_estimate
  ) values (
    v_sub.id,
    p_question_id,
    v_text,
    public._pc_word_count(v_text),
    greatest(1, length(v_text) / 4)
  )
  on conflict (submission_id, question_id) do update
    set prompt_text = excluded.prompt_text,
        word_count = excluded.word_count,
        token_estimate = excluded.token_estimate;

  select count(*) into v_resp_count from public.pc_responses where submission_id = v_sub.id;
  if v_resp_count >= 5 then
    update public.pc_submissions
    set status = 'SUBMITTED', submitted_at = now(), updated_at = now()
    where id = v_sub.id;
    update public.pc_participants
    set status = 'SUBMITTED', submitted_at = now(), updated_at = now()
    where id = v_p.id;
    return jsonb_build_object(
      'submission_id', v_sub.id,
      'status', 'SUBMITTED',
      'message', 'Your responses have been saved. Evaluation starts when an administrator runs it.'
    );
  end if;

  v_remaining := 5 - v_resp_count;
  return jsonb_build_object(
    'submission_id', v_sub.id,
    'status', 'PARTIAL',
    'message', format(
      'Prompt saved. %s prompt%s remaining.',
      v_remaining,
      case when v_remaining = 1 then '' else 's' end
    )
  );
end;
$$;

create or replace function public.pc_public_leaderboard(p_competition_id text)
returns jsonb
language plpgsql
stable
security definer
set search_path = public, extensions
as $$
declare
  v_visible boolean;
begin
  select leaderboard_visible into v_visible
  from public.pc_competitions
  where id = p_competition_id;
  if v_visible is distinct from true then
    return jsonb_build_object('visible', false, 'entries', '[]'::jsonb);
  end if;

  return jsonb_build_object(
    'visible', true,
    'entries',
    coalesce((
      with ranked as (
        select
          s.id,
          s.total_score,
          coalesce(p.display_name, 'Participant') as display_name,
          rank() over (order by s.total_score desc) as rank
        from public.pc_submissions s
        join public.pc_participants p on p.id = s.participant_id
        where s.competition_id = p_competition_id
          and s.status = 'COMPLETED'
          and s.total_score is not null
          and coalesce(p.is_pipeline_tester, false) = false
          and lower(public._pc_norm_reg(p.registration_number)) <> 'abhinavkumarsaksena'
      ),
      cats as (
        select
          r.id as submission_id,
          q.question_number,
          ev.score
        from ranked r
        join public.pc_responses resp on resp.submission_id = r.id
        join public.pc_questions q on q.id = resp.question_id
        join lateral (
          select e.score
          from public.pc_evaluations e
          where e.response_id = resp.id
            and e.score is not null
          order by e.created_at desc
          limit 1
        ) ev on true
      )
      select jsonb_agg(
        jsonb_build_object(
          'rank', x.rank,
          'display_name', x.display_name,
          'total_score', x.total_score,
          'category_scores', x.category_scores,
          'average_score', x.average_score
        )
        order by x.rank, x.display_name
      )
      from (
        select
          ranked.rank,
          ranked.display_name,
          ranked.total_score,
          coalesce(
            (
              select jsonb_object_agg(c.question_number::text, c.score)
              from cats c
              where c.submission_id = ranked.id
            ),
            '{}'::jsonb
          ) as category_scores,
          (
            select round(avg(c.score)::numeric, 2)
            from cats c
            where c.submission_id = ranked.id
          ) as average_score
        from ranked
      ) x
    ), '[]'::jsonb)
  );
end;
$$;

-- ---------------------------------------------------------------------------
-- Privileges: helpers stay internal; public RPCs are executable by anon.
-- Postgres grants EXECUTE to PUBLIC by default — revoke that first.
-- ---------------------------------------------------------------------------

revoke all on function public._pc_norm_reg(text) from public;
revoke all on function public._pc_norm_qr(text) from public;
revoke all on function public._pc_hash_session(text) from public;
revoke all on function public._pc_word_count(text) from public;
revoke all on function public._pc_can_skip_qr(public.pc_participants) from public;
revoke all on function public._pc_issue_session(public.pc_participants, text, text) from public;
revoke all on function public._pc_participant_from_session(text) from public;
revoke all on function public._pc_ensure_participant_from_reg(text, public.registrations) from public;

revoke all on function public.pc_login_registration(text, text) from public;
revoke all on function public.pc_login_qr(text, text, text) from public;
revoke all on function public.pc_submission_exists(text) from public;
revoke all on function public.pc_submit(text, text, jsonb) from public;
revoke all on function public.pc_submit_one(text, text, text, text) from public;
revoke all on function public.pc_public_leaderboard(text) from public;

grant execute on function public.pc_login_registration(text, text) to anon, authenticated;
grant execute on function public.pc_login_qr(text, text, text) to anon, authenticated;
grant execute on function public.pc_submission_exists(text) to anon, authenticated;
grant execute on function public.pc_submit(text, text, jsonb) to anon, authenticated;
grant execute on function public.pc_submit_one(text, text, text, text) to anon, authenticated;
grant execute on function public.pc_public_leaderboard(text) to anon, authenticated;

notify pgrst, 'reload schema';
