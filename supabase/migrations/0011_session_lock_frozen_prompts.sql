-- ============================================================================
-- Master Prompters 2.0: one active login + freeze saved prompts
-- ADDITIVE. Does not modify registrations / events / checkins.
-- ============================================================================

alter table public.pc_participants
  add column if not exists session_expires_at timestamptz;

-- ---------------------------------------------------------------------------
-- Freeze: insert a prompt once; identical retries are allowed; edits are not.
-- ---------------------------------------------------------------------------
create or replace function public._pc_save_frozen_response(
  p_submission_id uuid,
  p_question_id text,
  p_text text
)
returns void
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  v_existing text;
begin
  select prompt_text into v_existing
  from public.pc_responses
  where submission_id = p_submission_id
    and question_id = p_question_id;

  if found then
    if trim(v_existing) is not distinct from p_text then
      return;
    end if;
    raise exception 'This prompt is already saved and cannot be changed.';
  end if;

  insert into public.pc_responses (
    submission_id, question_id, prompt_text, word_count, token_estimate
  ) values (
    p_submission_id,
    p_question_id,
    p_text,
    public._pc_word_count(p_text),
    greatest(1, length(p_text) / 4)
  );
end;
$$;

create or replace function public._pc_participant_from_session(p_session_token text)
returns public.pc_participants
language plpgsql
stable
security definer
set search_path = public, pg_catalog
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
  if v_row.session_expires_at is not null and v_row.session_expires_at <= now() then
    raise exception 'Please sign in again.' using errcode = '28000';
  end if;
  return v_row;
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
  v_hash text;
  v_expires timestamptz;
  v_already boolean;
  v_sub_status text;
  v_done boolean;
  v_tester boolean;
  v_n int;
begin
  select s.status
  into v_sub_status
  from public.pc_submissions s
  where s.participant_id = p_participant.id
    and s.competition_id = p_competition_id
  limit 1;

  v_already := found;
  v_done := v_sub_status in ('SUBMITTED', 'COMPLETED')
    or p_participant.status = 'SUBMITTED';
  v_tester := coalesce(p_participant.is_pipeline_tester, false);

  v_token := 'pcs_' || replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '');
  v_hash := public._pc_hash_session(v_token);
  v_expires := now() + interval '8 hours';

  if v_tester or v_done then
    update public.pc_participants
    set
      session_token_hash = v_hash,
      session_expires_at = v_expires,
      login_count = coalesce(login_count, 0) + 1,
      last_login_at = now(),
      updated_at = now()
    where id = p_participant.id;
  else
    update public.pc_participants
    set
      session_token_hash = v_hash,
      session_expires_at = v_expires,
      login_count = coalesce(login_count, 0) + 1,
      last_login_at = now(),
      updated_at = now()
    where id = p_participant.id
      and (
        session_token_hash is null
        or session_expires_at is null
        or session_expires_at <= now()
      );
    get diagnostics v_n = row_count;
    if v_n = 0 then
      raise exception 'This registration is already signed in on another device. Continue there, or sign out first.';
    end if;
  end if;

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

create or replace function public.pc_logout(p_session_token text)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  v_hash text;
begin
  if public._pc_norm_reg(coalesce(p_session_token, '')) = '' then
    return jsonb_build_object('ok', true);
  end if;
  v_hash := public._pc_hash_session(p_session_token);
  update public.pc_participants
  set
    session_token_hash = null,
    session_expires_at = null,
    updated_at = now()
  where session_token_hash = v_hash;
  return jsonb_build_object('ok', true);
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
set search_path = public, pg_catalog
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

    perform public._pc_save_frozen_response(v_sub.id, v_qid, v_text);
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
set search_path = public, pg_catalog
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

  perform public._pc_save_frozen_response(v_sub.id, p_question_id, v_text);

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

revoke all on function public._pc_save_frozen_response(uuid, text, text) from public;
revoke all on function public._pc_participant_from_session(text) from public;
revoke all on function public._pc_issue_session(public.pc_participants, text, text) from public;
revoke all on function public.pc_logout(text) from public;
revoke all on function public.pc_submit(text, text, jsonb) from public;
revoke all on function public.pc_submit_one(text, text, text, text) from public;

grant execute on function public.pc_logout(text) to anon, authenticated;
grant execute on function public.pc_submit(text, text, jsonb) to anon, authenticated;
grant execute on function public.pc_submit_one(text, text, text, text) to anon, authenticated;

notify pgrst, 'reload schema';
