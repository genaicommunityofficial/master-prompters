/** Per-prompt character limits. Enforced in the form, API, and submit RPCs. */
export const PROMPT_MIN_CHARS = 20
export const PROMPT_MAX_CHARS = 2000

export function promptLimitCopy(min = PROMPT_MIN_CHARS, max = PROMPT_MAX_CHARS): string {
  return `${min}–${max} characters`
}

export function promptCharCount(text: string): number {
  return text.trim().length
}

export function isWithinPromptLimits(
  text: string,
  min: number = PROMPT_MIN_CHARS,
  max: number = PROMPT_MAX_CHARS,
): boolean {
  const n = promptCharCount(text)
  return n >= min && n <= max
}

export function promptLengthHint(
  len: number,
  min: number = PROMPT_MIN_CHARS,
  max: number = PROMPT_MAX_CHARS,
): string {
  if (len < min) return `Minimum ${min} characters`
  if (len > max) return `Over the ${max} character limit`
  return 'Ready'
}
