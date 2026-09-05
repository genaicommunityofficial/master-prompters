export type CategoryBrief = {
  n: number
  title: string
  brief: string
}

/** What to write in each live category. Matched by number, then title. */
export const CATEGORIES: CategoryBrief[] = [
  {
    n: 1,
    title: 'Meme Generation',
    brief:
      'Write a prompt that would produce an original, shareable meme. Name the joke, the visual setup or template, the on-screen text, the tone, and the audience. It should read instantly on a phone and stay funny on a second look.',
  },
  {
    n: 2,
    title: 'AI Visual Art Creation',
    brief:
      'Direct an image model as if you were briefing an illustrator. Specify subject, composition, lighting, palette, medium, and mood in enough detail that two people would picture the same artwork.',
  },
  {
    n: 3,
    title: 'AI Digital Storytelling / Creative Writing',
    brief:
      'Write a prompt for a short story or scene. Include character, setting, conflict, narrative voice, and how it should end. Name the genre, approximate length, and any language or point-of-view constraints.',
  },
  {
    n: 4,
    title: 'AI Song Factory',
    brief:
      'Write a prompt for an original song. Specify genre, mood or tempo, song structure (verse, chorus, bridge), vocal character, and the feeling the track should leave. Include a line of lyric direction if it helps.',
  },
  {
    n: 5,
    title: 'AI-Generated Poetry in Local Languages',
    brief:
      'Write a prompt for a poem in an Indian or regional language you name clearly. Specify the form (free verse, ghazal, haiku, and so on), the central images, and what the poem should mean.',
  },
]

export function briefForQuestion(title: string, questionNumber?: number): string | null {
  if (questionNumber) {
    const byNumber = CATEGORIES.find((c) => c.n === questionNumber)
    if (byNumber) return byNumber.brief
  }
  const needle = title.trim().toLowerCase()
  return CATEGORIES.find((c) => c.title.toLowerCase() === needle)?.brief ?? null
}
