import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type SessionRole = 'participant' | 'admin' | null

interface SessionState {
  token: string | null
  displayName: string
  email: string | null
  vitReg: string | null
  competitionId: string
  role: SessionRole
  setSession: (partial: Partial<SessionState>) => void
  clear: () => void
}

export const useSession = create<SessionState>()(
  persist(
    (set) => ({
      token: null,
      displayName: '',
      email: null,
      vitReg: null,
      competitionId: '',
      role: null,
      setSession: (partial) => set(partial),
      clear: () =>
        set({
          token: null,
          displayName: '',
          email: null,
          vitReg: null,
          competitionId: '',
          role: null,
        }),
    }),
    {
      name: 'pc_session_v1',
      version: 2,
    },
  ),
)
