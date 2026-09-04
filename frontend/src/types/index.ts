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
  cost: {
    total_evaluations: number
    total_input_tokens: number
    total_output_tokens: number
    total_thinking_tokens: number
    estimated_cost_usd: number
    per_model: Record<string, CostModelRow>
  }
  per_category: Record<string, CategoryStat>
}

export interface TestSuiteStatus {
  participants: number
  submissions: number
  responses: number
  evaluated: number
  pending: number
}

export interface LlmModeResponse {
  mode: 'dummy' | 'gemini'
  message?: string
}

export interface SeedResult {
  success: boolean
  participants: number
  submissions: number
  responses: number
}

export interface CleanupResult {
  success: boolean
  participants: number
  submissions: number
  responses: number
  jobs: number
  evaluations: number
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