export const LIVE_COMPETITION_ID = 'competition_2026'
export const TEST_COMPETITION_ID = 'competition_test'
export const ADMIN_TEST_MODE_KEY = 'pc_admin_test_mode'

export const API_BASE: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || '/api'

export const EVAL_BATCH_SIZE = 16
export const EVAL_CONCURRENCY = 8
export const EVAL_MAX_RETRIES = 3

export const CATEGORIES = [
  { n: 1, label: 'Meme Generation' },
  { n: 2, label: 'AI Visual Art Creation' },
  { n: 3, label: 'AI Digital Storytelling / Creative Writing' },
  { n: 4, label: 'AI Song Factory' },
  { n: 5, label: 'AI-Generated Poetry in Local Languages' },
]
