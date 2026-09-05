import { createClient, type SupabaseClient } from '@supabase/supabase-js'

let client: SupabaseClient | null = null

export function supabaseBrowser(): SupabaseClient {
  const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
  const anon = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined
  if (!url || !anon) {
    throw new Error('Supabase is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.')
  }
  if (!client) {
    client = createClient(url, anon, {
      auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
    })
  }
  return client
}
