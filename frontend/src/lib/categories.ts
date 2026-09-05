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
    brief: 'The joke, the frame, the punch.',
  },
  {
    n: 2,
    title: 'AI Visual Art Creation',
    brief: 'Subject, light, medium.',
  },
  {
    n: 3,
    title: 'AI Digital Storytelling / Creative Writing',
    brief: 'Character, place, voice.',
  },
  {
    n: 4,
    title: 'AI Song Factory',
    brief: 'Genre, mood, lyric.',
  },
  {
    n: 5,
    title: 'AI-Generated Poetry in Local Languages',
    brief: 'Language, form, image.',
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
