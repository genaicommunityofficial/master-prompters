-- ============================================================================
-- Public leaderboard includes registration number.
-- ADDITIVE. Does not modify registrations / events / checkins.
-- ============================================================================

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
          nullif(public._pc_norm_reg(p.registration_number), '') as registration_number,
          rank() over (order by s.total_score desc) as rank
        from public.pc_submissions s
        join public.pc_participants p on p.id = s.participant_id
        where s.competition_id = p_competition_id
          and s.status = 'COMPLETED'
          and s.total_score is not null
          and coalesce(p.is_pipeline_tester, false) = false
          and coalesce(p.status, '') is distinct from 'DISQUALIFIED'
          and lower(public._pc_norm_reg(p.registration_number)) <> 'abhinavkumarsaksena'
      ),
      top as (
        select *
        from ranked
        order by rank, display_name
        limit 50
      ),
      cats as (
        select
          r.id as submission_id,
          q.question_number,
          ev.score
        from top r
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
          'registration_number', x.registration_number,
          'total_score', x.total_score,
          'category_scores', x.category_scores,
          'average_score', x.average_score
        )
        order by x.rank, x.display_name
      )
      from (
        select
          top.rank,
          top.display_name,
          top.registration_number,
          top.total_score,
          coalesce(
            (
              select jsonb_object_agg(c.question_number::text, c.score)
              from cats c
              where c.submission_id = top.id
            ),
            '{}'::jsonb
          ) as category_scores,
          (
            select round(avg(c.score)::numeric, 2)
            from cats c
            where c.submission_id = top.id
          ) as average_score
        from top
      ) x
    ), '[]'::jsonb)
  );
end;
$$;

revoke all on function public.pc_public_leaderboard(text) from public;
grant execute on function public.pc_public_leaderboard(text) to anon, authenticated;

notify pgrst, 'reload schema';
