import type {
  AdminLoginResponse,
  Analytics,
  AuthResponse,
  CleanupResult,
  Competition,
  CompetitionDetail,
  CriteriaDetail,
  CriteriaEntry,
  DashboardMetrics,
  LeaderboardResponse,
  LiveLogsResponse,
  LiveStats,
  LlmModeResponse,
  ManualRegistration,
  PromptInput,
  SeedResult,
  SubmissionReceipt,
  EvalLogEntry,
  EvalRunStatus,
  TestSuiteStatus,
} from '@/types'

const API_BASE: string = (import.meta.env.VITE_API_BASE_URL as string) ?? '/api'

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

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
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
      if (body.detail) message = body.detail
    } catch {
      /* ignore */
    }
    throw new ApiError(message, res.status)
  }
  return res.json() as Promise<T>
}

export const api = {
  getActiveCompetition: () => request<Competition>('/competitions/active'),
  getCompetition: (id: string) => request<CompetitionDetail>(`/competitions/${id}`),
  loginWithQrImage: (competitionId: string, file: File) => {
    const form = new FormData()
    form.append('image', file)
    return request<AuthResponse>(`/auth/login/qr?competition_id=${competitionId}`, {
      method: 'POST',
      body: form,
    })
  },
  loginWithQrMessage: (competitionId: string, qrMessage: string) =>
    request<AuthResponse>('/auth/login/message', {
      method: 'POST',
      body: JSON.stringify({ competition_id: competitionId, qr_message: qrMessage }),
    }),
  loginWithTest: (competitionId: string, identifier: string) =>
    request<AuthResponse>('/auth/login/test', {
      method: 'POST',
      body: JSON.stringify({ competition_id: competitionId, identifier }),
    }),
  loginWithRegistrationNumber: (competitionId: string, registrationNumber: string) =>
    request<AuthResponse>('/auth/login/registration-number', {
      method: 'POST',
      body: JSON.stringify({
        competition_id: competitionId,
        registration_number: registrationNumber,
      }),
    }),
  submit: (competitionId: string, prompts: PromptInput[]) =>
    request<SubmissionReceipt>('/submissions', {
      method: 'POST',
      body: JSON.stringify({
        competition_id: competitionId,
        prompts,
      }),
    }),
  submitIndividual: (competitionId: string, prompt: PromptInput) =>
    request<SubmissionReceipt>('/submissions/individual', {
      method: 'POST',
      body: JSON.stringify({
        competition_id: competitionId,
        ...prompt,
      }),
    }),
  submissionExists: () => request<{ submitted: boolean }>('/submissions/exists'),
  leaderboard: (competitionId: string) =>
    request<LeaderboardResponse>(`/leaderboard/${competitionId}`),

  // ---- Admin ----
  adminLogin: (username: string, password: string) =>
    request<AdminLoginResponse>(
      '/admin/login',
      { method: 'POST', body: JSON.stringify({ username, password }) },
      null,
    ),
  adminDashboard: (token?: string) =>
    request<{ metrics: DashboardMetrics }>('/admin/dashboard', {}, token ?? getAdminToken()),
  adminSubmissions: (token?: string) =>
    request<unknown[]>('/admin/submissions', {}, token ?? getAdminToken()),
  adminEvaluations: (token?: string) =>
    request<unknown[]>('/admin/evaluations', {}, token ?? getAdminToken()),
  adminStartEval: (
    body: {
      competition_id?: string
      batch_size?: number
      concurrency?: number
      max_retries?: number
      llm_mode?: string
    },
    token?: string,
  ) =>
    request<EvalRunStatus>(
      '/admin/evaluations/start',
      { method: 'POST', body: JSON.stringify(body) },
      token ?? getAdminToken(),
    ),
  adminEvalRun: (token?: string) =>
    request<EvalRunStatus>('/admin/evaluations/run', {}, token ?? getAdminToken()),
  adminEvalLogs: (since = 0, token?: string) =>
    request<{ logs: EvalLogEntry[]; run: EvalRunStatus }>(
      `/admin/evaluations/logs?since=${since}`,
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
  adminAnalytics: (token?: string) =>
    request<{ analytics: Analytics }>('/admin/analytics', {}, token ?? getAdminToken()),
  adminTestCleanup: (token?: string) =>
    request<CleanupResult>('/admin/test/cleanup', { method: 'POST' }, token ?? getAdminToken()),
  adminSeedTestData: (participantCount: number, token?: string) =>
    request<SeedResult>(
      '/admin/test/seed',
      { method: 'POST', body: JSON.stringify({ participant_count: participantCount }) },
      token ?? getAdminToken(),
    ),
  adminTestStatus: (token?: string) =>
    request<TestSuiteStatus>('/admin/test/status', {}, token ?? getAdminToken()),
  adminGetLlmMode: (token?: string) =>
    request<LlmModeResponse>('/admin/test/llm-mode', {}, token ?? getAdminToken()),
  adminSetLlmMode: (mode: 'dummy' | 'gemini', token?: string) =>
    request<LlmModeResponse>(
      '/admin/test/llm-mode',
      { method: 'POST', body: JSON.stringify({ mode }) },
      token ?? getAdminToken(),
    ),
  adminPublishLeaderboard: (token?: string) =>
    request<{ success: boolean; visible: boolean }>('/admin/leaderboard/publish', { method: 'POST' }, token ?? getAdminToken()),
  adminUnpublishLeaderboard: (token?: string) =>
    request<{ success: boolean; visible: boolean }>('/admin/leaderboard/unpublish', { method: 'POST' }, token ?? getAdminToken()),
  adminOpenCompetition: (token?: string) =>
    request<{ success: boolean; status: string | null }>('/admin/competition/open', { method: 'POST' }, token ?? getAdminToken()),
  adminCloseCompetition: (token?: string) =>
    request<{ success: boolean; status: string | null }>('/admin/competition/close', { method: 'POST' }, token ?? getAdminToken()),
  adminCriteriaList: (token?: string) =>
    request<CriteriaEntry[]>('/admin/criteria', {}, token ?? getAdminToken()),
  adminCriteriaDetail: (category: number, token?: string) =>
    request<CriteriaDetail>(`/admin/criteria/${category}`, {}, token ?? getAdminToken()),
  adminCriteriaUpload: (category: number, file: File, token?: string) => {
    const form = new FormData()
    form.append('category', String(category))
    form.append('file', file)
    return request<CriteriaEntry>(
      `/admin/criteria?category=${category}`,
      { method: 'POST', body: form },
      token ?? getAdminToken(),
    )
  },
  adminExportUrl: (category?: number) =>
    `/admin/export/csv${category ? `?category=${category}` : ''}`,
  adminListRegistrations: (token?: string) =>
    request<ManualRegistration[]>('/admin/registrations', {}, token ?? getAdminToken()),
  adminCreateRegistration: (
    body: { registration_number: string; display_name?: string; email?: string },
    token?: string,
  ) =>
    request<{ success: boolean; id: string; registration_number?: string; display_name?: string }>(
      '/admin/registrations',
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