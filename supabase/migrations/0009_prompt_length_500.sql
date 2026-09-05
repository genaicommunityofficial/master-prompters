-- ============================================================================
-- Master Prompters 2.0: prompt length 20–500 characters
-- ADDITIVE. Updates pc_questions only. Does not modify registrations / events.
-- ============================================================================

alter table public.pc_questions
  alter column max_length set default 500;

update public.pc_questions
set
  min_length = 20,
  max_length = 500,
  description = case question_number
    when 1 then 'Write a prompt that would produce an original, shareable meme. Name the joke, the visual setup or template, the on-screen text, the tone, and the audience. It should read instantly on a phone and stay funny on a second look.'
    when 2 then 'Direct an image model as if you were briefing an illustrator. Specify subject, composition, lighting, palette, medium, and mood in enough detail that two people would picture the same artwork.'
    when 3 then 'Write a prompt for a short story or scene. Include character, setting, conflict, narrative voice, and how it should end. Name the genre, approximate length, and any language or point-of-view constraints.'
    when 4 then 'Write a prompt for an original song. Specify genre, mood or tempo, song structure (verse, chorus, bridge), vocal character, and the feeling the track should leave. Include a line of lyric direction if it helps.'
    when 5 then 'Write a prompt for a poem in an Indian or regional language you name clearly. Specify the form (free verse, ghazal, haiku, and so on), the central images, and what the poem should mean.'
    else description
  end
where competition_id in ('competition_2026', 'competition_test');
