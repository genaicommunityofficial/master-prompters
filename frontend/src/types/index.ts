export interface Competition {
  id: string
  name: string
  slug: string
  description: string | null
  status: string
  start_at: string | null
  end_at: string | null
  leaderboard_visible: boolean
  competition_status_open: boolean
}

export interface Question {
  id: string
  question_number: number
  title: string
  description: string | null
  max_length: number
  min_length: number
}

export interface CompetitionDetail extends Competition {
  questions: Question[]
}

export interface ParticipantInfo {
  competition_id: string
  participant_id: string
  display_name: string
  email: string | null
  vit_registration_number: string | null
  already_submitted: boolean
}

export interface AuthResponse {
  token: string
  participant: ParticipantInfo
}

export interface LoginPrepareResponse {
  requires_qr: boolean
  token: string | null
  participant: ParticipantInfo | null
  display_name: string | null
}

export interface PromptInput {
  question_id: string
  prompt_text: string
  competition_id?: string
}

export interface SubmissionReceipt {
  submission_id: string
  status: string
  message: string
}

export interface LeaderboardEntry {
  rank: number
  display_name: string
  total_score: number
  category_scores?: Record<number, number>
  average_score?: number | null
}

export interface LeaderboardResponse {
  visible: boolean
  entries: LeaderboardEntry[]
}

export interface ManualRegistration {
  id: string
  registration_number: string | null
  display_name: string | null
  email: string | null
  status: string | null
  created_at: string | null
}

export interface ParticipantRosterRow {
  id: string
  registration_number: string | null
  display_name: string | null
  source: 'event' | 'added' | 'dataset'
  logged_in: boolean | null
  last_login_at: string | null
  submitted: boolean
  submission_status: string | null
}

export interface ParticipantRoster {
  competition_id: string
  test_mode: boolean
  show_login: boolean
  registered: number
  logged_in: number | null
  submitted: number
  completed: number
  participants: ParticipantRosterRow[]
}

export interface DashboardMetrics {
  competition_id: string
  competition_status?: string
  total_participants: number
  submitted: number
  completed: number
  failed: number
  total_prompts: number
  evaluated: number
  awaiting_eval?: number
  queued: number
  retrying: number
  evaluation_failed: number
  per_category?: Record<string, IntakeCategoryStat>
  avg_score: number | null
  median_score: number | null
  highest_score: number | null
  lowest_score: number | null
}

export interface AdminLoginResponse {
  token: string
  username: string
  role: string
}

export interface LiveStats {
  rps: number
  requests_last_60s: number
  avg_latency_ms: number
  error_count_60s: number
  window_seconds: number
}

export interface RequestLog {
  id: number
  request_id: string | null
  method: string
  path: string
  status: number
  latency_ms: number
  participant_id: string | null
  ip: string | null
  created_at: string
}

export interface LiveLogsResponse {
  logs: RequestLog[]
  stats: LiveStats
}

export interface CostModelRow {
  evaluations: number
  input_tokens: number
  output_tokens: number
  thinking_tokens: number
  cost_usd: number
}

export interface IntakeCategoryStat {
  question_number: number
  title: string
  stored: number
  evaluated: number
}

export interface CategoryStat {
  question_number: number
  title: string
  stored?: number
  evaluated: number
  avg_score: number | null
  min_score: number | null
  max_score: number | null
}

export interface EvalLogEntry {
  seq: number
  ts: number
  level: string
  message: string
}

export interface EvalRunStatus {
  status: string
  accepted?: boolean
  competition_id: string | null
  batch_size: number
  concurrency: number
  max_retries: number
  enqueued: number
  processed: number
  completed: number
  failed: number
  started_at: number | null
  finished_at: number | null
  error_message: string | null
}

export interface Analytics {
  competition_id: string
  dashboard: DashboardMetrics
  cost: EvalCostSummary
  per_category: Record<string, CategoryStat>
}

export interface EvalCostSummary {
  total_evaluations: number
  total_input_tokens: number
  total_output_tokens: number
  total_thinking_tokens: number
  estimated_cost_usd: number
  per_model: Record<string, CostModelRow>
}

export interface EvalFailedJob {
  response_id: string | null
  attempt_count: number | null
  error: string
  question_number: number | null
}

export interface EvalRunSnapshot {
  status: string
  accepted?: boolean
  enqueued: number
  processed: number
  completed: number
  failed: number
  started_at: number | null
  finished_at: number | null
  error_message: string | null
  elapsed_seconds: number | null
  rate_per_second: number | null
  eta_seconds: number | null
}

export interface EvalProgress {
  competition_id: string
  competition_status: string | null
  leaderboard_visible: boolean
  totals: {
    participants: number
    submissions: number
    submitted: number
    completed: number
    failed: number
    job_failed?: number
    responses: number
    evaluated: number
    pending: number
    progress_pct: number
    avg_score: number | null
    median_score?: number | null
    highest_score?: number | null
    lowest_score?: number | null
  }
  jobs: {
    QUEUED: number
    PROCESSING: number
    RETRY: number
    COMPLETED: number
    FAILED: number
    total: number
  }
  failed_sample: EvalFailedJob[]
  top_errors: { message: string; count: number }[]
  per_category: Record<string, EvalProgressCategory>
  cost: EvalCostSummary
  run: EvalRunSnapshot | null
}

export interface EvalProgressCategory {
  question_number: number
  title: string
  stored: number
  evaluated: number
  progress_pct: number
  avg_score: number | null
  min_score?: number | null
  max_score?: number | null
}

export interface FunnelStage {
  count: number
  pct_of_registered?: number | null
  pct_of_logged_in?: number | null
  pct_of_submitted?: number | null
}

export interface ParticipationRow {
  participant_id: string
  display_name: string | null
  email: string | null
  registration_number: string | null
  status: string | null
  login_count: number
  last_login_at: string | null
  submitted: boolean
  submission_status: string | null
  total_score: number | null
}

export interface ParticipationFunnel {
  competition_id: string
  registered: number
  logged_in: number
  logged_in_not_submitted: number
  submitted: number
  completed: number
  funnel: {
    registered: number
    logged_in: { count: number; pct_of_registered: number | null }
    submitted: { count: number; pct_of_logged_in: number | null }
    completed: { count: number; pct_of_submitted: number | null }
  }
  sources: {
    with_registration_number: number
    qr_only: number
  }
  participants: ParticipationRow[]
}

export interface CriteriaEntry {
  question_number: number
  file_name: string
  content_hash: string
  updated_at: string | null
}

export interface CriteriaDetail {
  question_number: number
  file_name: string | null
  content_md: string
}