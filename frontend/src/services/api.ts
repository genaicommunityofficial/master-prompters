import { decodeQrFromFile } from '@/lib/decodeQr'
import { usesDirectSupabase } from '@/lib/runtime'
import type {
  AdminLoginResponse,
  Analytics,
  AuthResponse,
  Competition,
  CompetitionDetail,
  CriteriaDetail,
  CriteriaEntry,
  DashboardMetrics,
  EvalLogEntry,
  EvalProgress,
  EvalRunStatus,
  LeaderboardResponse,
  LiveLogsResponse,
  LiveStats,
  LoginPrepareResponse,
  ParticipantRoster,
  PromptInput,
  SubmissionReceipt,
} from '@/types'
import { ApiError } from './errors'
import { participantSupabase } from './participantSupabase'

export { ApiError }

const API_BASE: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || '/api'

const TOKEN_KEY = 'pc_token'
const ADMIN_TOKEN_KEY = 'pc_admin_token'

export function getToken(): string | null {
  return typeof window !== 'undefined' ? window.localStorage.getItem(TOKEN_KEY) : null
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token)
}

export function getAdminToken(): string | null {
  return typeof window !== 'undefined' ? window.localStorage.getItem(ADMIN_TOKEN_KEY) : null
}

export function setAdminToken(token: string): void {
  window.localStorage.setItem(ADMIN_TOKEN_KEY, token)
}

export function clearSession(): void {
  window.localStorage.removeItem(TOKEN_KEY)
}

export function clearAdminSession(): void {
  window.localStorage.removeItem(ADMIN_TOKEN_KEY)
}

function withComp(path: string, competitionId?: string, extra?: Record<string, string | number | undefined>) {
  const params = new URLSearchParams()
  if (competitionId) params.set('competition_id', competitionId)
  for (const [key, value] of Object.entries(extra ?? {})) {
    if (value !== undefined && value !== '') params.set(key, String(value))
  }
  const qs = params.toString()
  return qs ? `${path}?${qs}` : path
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  token?: string | null,
): Promise<T> {
  const headers = new Headers(init.headers)
  const authToken = token !== undefined ? token : getToken()
  if (authToken) headers.set('Authorization', `Bearer ${authToken}`)
  if (init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers })
  if (!res.ok) {
    let message = 'Something went wrong. Please try again.'
    try {
      const body = (await res.json()) as { detail?: string }
      if (typeof body.detail === 'string') message = body.detail
    } catch {
      /* ignore */
    }
    throw new ApiError(message, res.status)
  }
  return res.json() as Promise<T>
}

export const api = {
  getActiveCompetition: () =>
    usesDirectSupabase()
      ? participantSupabase.getActiveCompetition()
      : request<Competition>('/competitions/active'),
  getCompetition: (id: string) =>
    usesDirectSupabase()
      ? participantSupabase.getCompetition(id)
      : request<CompetitionDetail>(`/competitions/${id}`),
  loginWithQrImage: async (competitionId: string, registrationNumber: string, file: File) => {
    if (usesDirectSupabase()) {
      const qrMessage = await decodeQrFromFile(file)
      return participantSupabase.loginWithQrMessage(competitionId, registrationNumber, qrMessage)
    }
    const form = new FormData()
    form.append('image', file)
    return request<AuthResponse>(
      withComp('/auth/login/qr', competitionId, { registration_number: registrationNumber }),
      { method: 'POST', body: form },
    )
  },
  loginWithQrMessage: (competitionId: string, registrationNumber: string, qrMessage: string) =>
    usesDirectSupabase()
      ? participantSupabase.loginWithQrMessage(competitionId, registrationNumber, qrMessage)
      : request<AuthResponse>('/auth/login/message', {
          method: 'POST',
          body: JSON.stringify({
            competition_id: competitionId,
            registration_number: registrationNumber,
            qr_message: qrMessage,
          }),
        }),
  loginWithRegistrationNumber: (competitionId: string, registrationNumber: string) =>
    usesDirectSupabase()
      ? participantSupabase.loginWithRegistrationNumber(competitionId, registrationNumber)
      : request<LoginPrepareResponse>('/auth/login/registration-number', {
          method: 'POST',
          body: JSON.stringify({
            competition_id: competitionId,
            registration_number: registrationNumber,
          }),
        }),
  logout: () =>
    usesDirectSupabase()
      ? participantSupabase.logout(getToken())
      : request<{ ok: boolean }>('/auth/logout', { method: 'POST' }),
  submit: (competitionId: string, prompts: PromptInput[]) =>
    usesDirectSupabase()
      ? participantSupabase.submit(competitionId, prompts, getToken())
      : request<SubmissionReceipt>('/submissions', {
          method: 'POST',
          body: JSON.stringify({
            competition_id: competitionId,
            prompts,
          }),
        }),
  submitIndividual: (competitionId: string, prompt: PromptInput) =>
    usesDirectSupabase()
      ? participantSupabase.submitIndividual(competitionId, prompt, getToken())
      : request<SubmissionReceipt>('/submissions/individual', {
          method: 'POST',
          body: JSON.stringify({
            competition_id: competitionId,
            ...prompt,
          }),
        }),
  submissionExists: () =>
    usesDirectSupabase()
      ? participantSupabase.submissionExists(getToken())
      : request<{ submitted: boolean }>('/submissions/exists'),
  leaderboard: (competitionId: string) =>
    usesDirectSupabase()
      ? participantSupabase.leaderboard(competitionId)
      : request<LeaderboardResponse>(`/leaderboard/${competitionId}`),

  adminLogin: (username: string, password: string) =>
    request<AdminLoginResponse>(
      '/admin/login',
      { method: 'POST', body: JSON.stringify({ username, password }) },
      null,
    ),
  adminDashboard: (competitionId: string, token?: string) =>
    request<{ metrics: DashboardMetrics }>(
      withComp('/admin/dashboard', competitionId),
      {},
      token ?? getAdminToken(),
    ),
  adminStartEval: (
    body: {
      competition_id?: string
      batch_size?: number
      concurrency?: number
      max_retries?: number
      mode?: 'restart' | 'resume' | 'retry_failed'
    },
    token?: string,
  ) =>
    request<EvalRunStatus>(
      '/admin/evaluations/start',
      { method: 'POST', body: JSON.stringify(body) },
      token ?? getAdminToken(),
    ),
  adminPauseEval: (token?: string) =>
    request<EvalRunStatus>(
      '/admin/evaluations/pause',
      { method: 'POST', body: JSON.stringify({}) },
      token ?? getAdminToken(),
    ),
  adminEvalRun: (token?: string) =>
    request<EvalRunStatus>('/admin/evaluations/run', {}, token ?? getAdminToken()),
  adminEvalStatus: (competitionId: string, token?: string) =>
    request<EvalProgress>(
      withComp('/admin/eval-status', competitionId),
      {},
      token ?? getAdminToken(),
    ),
  adminLeaderboard: (competitionId: string, token?: string) =>
    request<LeaderboardResponse>(
      withComp('/admin/leaderboard', competitionId),
      {},
      token ?? getAdminToken(),
    ),
  adminParticipants: (competitionId: string, token?: string) =>
    request<ParticipantRoster>(
      withComp('/admin/participants', competitionId),
      {},
      token ?? getAdminToken(),
    ),
  adminEvalLogs: (since = 0, token?: string) =>
    request<{ logs: EvalLogEntry[]; run: EvalRunStatus }>(
      `/admin/evaluations/logs?since=${since}&limit=200`,
      {},
      token ?? getAdminToken(),
    ),
  adminLiveStats: (token?: string) =>
    request<LiveStats>('/admin/monitor/live', {}, token ?? getAdminToken()),
  adminLiveLogs: (since?: string, token?: string) =>
    request<LiveLogsResponse>(
      `/admin/monitor/logs${since ? `?since_ts=${encodeURIComponent(since)}` : ''}`,
      {},
      token ?? getAdminToken(),
    ),
  adminAnalytics: (competitionId: string, token?: string) =>
    request<{ analytics: Analytics }>(
      withComp('/admin/analytics', competitionId),
      {},
      token ?? getAdminToken(),
    ),
  adminPublishLeaderboard: (competitionId: string, token?: string) =>
    request<{ success: boolean; visible: boolean }>(
      withComp('/admin/leaderboard/publish', competitionId),
      { method: 'POST' },
      token ?? getAdminToken(),
    ),
  adminUnpublishLeaderboard: (competitionId: string, token?: string) =>
    request<{ success: boolean; visible: boolean }>(
      withComp('/admin/leaderboard/unpublish', competitionId),
      { method: 'POST' },
      token ?? getAdminToken(),
    ),
  adminOpenCompetition: (competitionId: string, token?: string) =>
    request<{ success: boolean; status: string | null }>(
      withComp('/admin/competition/open', competitionId),
      { method: 'POST' },
      token ?? getAdminToken(),
    ),
  adminCloseCompetition: (competitionId: string, token?: string) =>
    request<{ success: boolean; status: string | null }>(
      withComp('/admin/competition/close', competitionId),
      { method: 'POST' },
      token ?? getAdminToken(),
    ),
  adminCriteriaList: (competitionId: string, token?: string) =>
    request<CriteriaEntry[]>(withComp('/admin/criteria', competitionId), {}, token ?? getAdminToken()),
  adminCriteriaDetail: (competitionId: string, category: number, token?: string) =>
    request<CriteriaDetail>(
      withComp(`/admin/criteria/${category}`, competitionId),
      {},
      token ?? getAdminToken(),
    ),
  adminCriteriaUpload: (competitionId: string, category: number, file: File, token?: string) => {
    const form = new FormData()
    form.append('file', file)
    return request<CriteriaEntry>(
      withComp('/admin/criteria', competitionId, { category }),
      { method: 'POST', body: form },
      token ?? getAdminToken(),
    )
  },
  adminCopyLiveCriteria: (competitionId: string, token?: string) =>
    request<{ success: boolean; copied: number }>(
      withComp('/admin/criteria/copy-live', competitionId),
      { method: 'POST' },
      token ?? getAdminToken(),
    ),
  adminExportUrl: (competitionId: string, category?: number) =>
    withComp('/admin/export/csv', competitionId, category ? { category } : undefined),
  adminCreateRegistration: (
    competitionId: string,
    body: { registration_number: string; display_name?: string; email?: string },
    token?: string,
  ) =>
    request<{ success: boolean; id: string; registration_number?: string; display_name?: string }>(
      withComp('/admin/registrations', competitionId),
      { method: 'POST', body: JSON.stringify(body) },
      token ?? getAdminToken(),
    ),
}

export function extractQrDetails(message: string): string {
  const trimmed = message.trim()
  const idx = trimmed.indexOf('GENAI_QR_')
  if (idx !== -1) return trimmed.slice(idx)
  return trimmed
}
