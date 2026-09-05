import type {
  AuthResponse,
  Competition,
  CompetitionDetail,
  LeaderboardResponse,
  LoginPrepareResponse,
  PromptInput,
  SubmissionReceipt,
} from '@/types'
import { ApiError } from './errors'
import { supabaseBrowser } from './supabaseClient'

const COMPETITION_COLUMNS =
  'id, name, slug, description, status, start_at, end_at, leaderboard_visible'
const QUESTION_COLUMNS = 'id, question_number, title, description, max_length, min_length'
const ACTIVE_SLUGS = ['master-prompters-2-0', 'default']

type CompetitionRow = {
  id: string
  name: string | null
  slug: string | null
  description: string | null
  status: string
  start_at: string | null
  end_at: string | null
  leaderboard_visible: boolean | null
}

type QuestionRow = {
  id: string
  question_number: number | null
  title: string | null
  description: string | null
  max_length: number | null
  min_length: number | null
}

function toCompetition(row: CompetitionRow): Competition {
  return {
    id: row.id,
    name: row.name || 'Competition',
    slug: row.slug || row.id,
    description: row.description,
    status: row.status,
    start_at: row.start_at,
    end_at: row.end_at,
    leaderboard_visible: Boolean(row.leaderboard_visible),
    competition_status_open: row.status === 'OPEN',
  }
}

function toQuestion(row: QuestionRow) {
  const number = row.question_number || 0
  return {
    id: row.id,
    question_number: number,
    title: row.title || `Question ${number}`,
    description: row.description,
    max_length: row.max_length ?? 500,
    min_length: row.min_length ?? 20,
  }
}

function rpcError(message: string, code?: string): ApiError {
  const status =
    code === '28000' || /sign in again|session/i.test(message) ? 401 : 400
  return new ApiError(message || 'Something went wrong. Please try again.', status)
}

async function rpc<T>(name: string, args: Record<string, unknown>): Promise<T> {
  const { data, error } = await supabaseBrowser().rpc(name, args)
  if (error) throw rpcError(error.message, error.code)
  return data as T
}

export const participantSupabase = {
  async getActiveCompetition(): Promise<Competition> {
    const client = supabaseBrowser()
    for (const slug of ACTIVE_SLUGS) {
      const { data, error } = await client
        .from('pc_competitions')
        .select(COMPETITION_COLUMNS)
        .eq('slug', slug)
        .maybeSingle()
      if (error) throw rpcError(error.message, error.code)
      if (data) return toCompetition(data as CompetitionRow)
    }
    throw new ApiError('No active competition.', 404)
  },

  async getCompetition(id: string): Promise<CompetitionDetail> {
    const client = supabaseBrowser()
    const { data: comp, error: compErr } = await client
      .from('pc_competitions')
      .select(COMPETITION_COLUMNS)
      .eq('id', id)
      .maybeSingle()
    if (compErr) throw rpcError(compErr.message, compErr.code)
    if (!comp) throw new ApiError('Competition not found.', 404)
    const { data: questions, error: qErr } = await client
      .from('pc_questions')
      .select(QUESTION_COLUMNS)
      .eq('competition_id', id)
      .order('question_number')
    if (qErr) throw rpcError(qErr.message, qErr.code)
    return {
      ...toCompetition(comp as CompetitionRow),
      questions: ((questions as QuestionRow[]) ?? []).map(toQuestion),
    }
  },

  loginWithRegistrationNumber: (competitionId: string, registrationNumber: string) =>
    rpc<LoginPrepareResponse>('pc_login_registration', {
      p_competition_id: competitionId,
      p_registration_number: registrationNumber,
    }),

  loginWithQrMessage: (competitionId: string, registrationNumber: string, qrMessage: string) =>
    rpc<AuthResponse>('pc_login_qr', {
      p_competition_id: competitionId,
      p_registration_number: registrationNumber,
      p_qr_message: qrMessage,
    }),

  submit: (competitionId: string, prompts: PromptInput[], token: string | null) =>
    rpc<SubmissionReceipt>('pc_submit', {
      p_session_token: token,
      p_competition_id: competitionId,
      p_prompts: prompts.map((p) => ({
        question_id: p.question_id,
        prompt_text: p.prompt_text,
      })),
    }),

  submitIndividual: (competitionId: string, prompt: PromptInput, token: string | null) =>
    rpc<SubmissionReceipt>('pc_submit_one', {
      p_session_token: token,
      p_competition_id: competitionId,
      p_question_id: prompt.question_id,
      p_prompt_text: prompt.prompt_text,
    }),

  submissionExists: (token: string | null) =>
    rpc<{ submitted: boolean }>('pc_submission_exists', {
      p_session_token: token,
    }),

  leaderboard: (competitionId: string) =>
    rpc<LeaderboardResponse>('pc_public_leaderboard', {
      p_competition_id: competitionId,
    }),
}
