/** Participant traffic talks to Supabase when the public anon env is set (Vercel). */
export function usesDirectSupabase(): boolean {
  return Boolean(import.meta.env.VITE_SUPABASE_URL && import.meta.env.VITE_SUPABASE_ANON_KEY)
}

/** Admin/eval FastAPI is local (Vite proxy) or an explicit API base URL. */
export function isAdminApiAvailable(): boolean {
  if (import.meta.env.DEV) return true
  const base = import.meta.env.VITE_API_BASE_URL as string | undefined
  return Boolean(base && base.trim())
}
