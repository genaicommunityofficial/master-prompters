import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, AlertCircle, CheckCircle2, Pencil } from 'lucide-react'
import { PageShell } from '@/components/layout'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Spinner, FullScreenLoader } from '@/components/ui/spinner'
import { api } from '@/services/api'
import { useSession } from '@/store/session'
import type { Question } from '@/types'
import { briefForQuestion } from '@/lib/categories'
import {
  PROMPT_MAX_CHARS,
  PROMPT_MIN_CHARS,
  isWithinPromptLimits,
  promptCharCount,
  promptLimitCopy,
} from '@/lib/promptLimits'
import { cn, wordCount } from '@/lib/utils'

const DRAFT_KEY = 'pc_draft_v2'

// Individual submission status tracking
interface SubmissionStatus {
  total: number
  submitted: number
  status: 'idle' | 'submitting' | 'complete' | 'error'
  currentQuestion: string | null
  error: string | null
}

export default function ReviewPage() {
  const nav = useNavigate()
  const competitionId = useSession((s) => s.competitionId)
  const token = useSession((s) => s.token)

  const [questions, setQuestions] = useState<Question[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Individual submission state
  const [submissionStatus, setSubmissionStatus] = useState<SubmissionStatus>({
    total: 0,
    submitted: 0,
    status: 'idle',
    currentQuestion: null,
    error: null,
  })

  const draft = useMemo<Record<string, string>>(() => {
    try {
      return JSON.parse(window.localStorage.getItem(DRAFT_KEY) ?? '{}')
    } catch {
      return {}
    }
  }, [])

  useEffect(() => {
    if (!token || !competitionId) {
      setLoading(false)
      nav('/', { replace: true, state: { loginRequired: true } })
      return
    }
    api
      .getCompetition(competitionId)
      .then((c) => setQuestions(c.questions))
      .catch(() => setError('Could not load the competition.'))
      .finally(() => setLoading(false))
  }, [token, competitionId, nav])

  const handleEdit = (questionId: string) => {
    // Persist the focused question id so the competition page can scroll to it.
    window.sessionStorage.setItem('pc_edit_focus', questionId)
    nav('/competition')
  }

  const allReady = useMemo(
    () =>
      questions.length === 5 &&
      questions.every((q) => isWithinPromptLimits(draft[q.id] ?? '')),
    [questions, draft],
  )

  const limitsLabel = promptLimitCopy()

  const handleSubmit = async () => {
    if (!competitionId) return
    if (!allReady) {
      setError(`Every prompt must be ${limitsLabel} before submitting.`)
      return
    }

    setError('')
    setSubmissionStatus({
      total: questions.length,
      submitted: 0,
      status: 'submitting',
      currentQuestion: null,
      error: null,
    })

    try {
      // Submit each prompt individually for faster response and reduced server load
      const results: Array<import('@/types').SubmissionReceipt | null> = []
      for (const q of questions) {
        setSubmissionStatus((prev) => ({
          ...prev,
          currentQuestion: q.title,
        }))

        try {
          const result = await api.submitIndividual(competitionId, {
            question_id: q.id,
            prompt_text: draft[q.id] ?? '',
          })
          results.push(result)
          setSubmissionStatus((prev) => ({
            ...prev,
            submitted: prev.submitted + 1,
          }))
        } catch (e) {
          // If individual submission fails, try batch submission as fallback
          console.error(`Individual submission failed for ${q.title}, trying batch...`, e)
          results.push(null)
        }
      }

      // Check if all submissions succeeded
      if (results.every((r) => r !== null)) {
        window.localStorage.removeItem(DRAFT_KEY)
        nav('/submitted', { state: { message: 'Your responses have been saved. Evaluation starts when an administrator runs it.' } })
      } else if (results.some((r) => r !== null)) {
        // Some succeeded, some failed - resubmit all five via batch. The API
        // upserts responses into any existing draft, so no work is lost.
        const prompts = questions.map((q) => ({
          question_id: q.id,
          prompt_text: draft[q.id] ?? '',
        }))
        try {
          await api.submit(competitionId, prompts)
          window.localStorage.removeItem(DRAFT_KEY)
          nav('/submitted', { state: { message: 'Your responses have been saved. Evaluation starts when an administrator runs it.' } })
          return
        } catch (batchErr) {
          setError(
            batchErr instanceof Error
              ? batchErr.message
              : 'Some prompts could not be submitted. Please try again.',
          )
          setSubmissionStatus((prev) => ({ ...prev, status: 'error' }))
          return
        }
      } else {
        // All individual submissions failed - try single batch submission
        const prompts = questions.map((q) => ({
          question_id: q.id,
          prompt_text: draft[q.id] ?? '',
        }))
        await api.submit(competitionId, prompts)
        window.localStorage.removeItem(DRAFT_KEY)
        nav('/submitted', { state: { message: 'Your responses have been saved. Evaluation starts when an administrator runs it.' } })
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'We could not submit your responses. Please try again.')
      setSubmissionStatus((prev) => ({ ...prev, status: 'error', error: String(e) }))
    }
  }

  if (loading) return <PageShell><FullScreenLoader label="Loading review" /></PageShell>

  const isSubmitting = submissionStatus.status === 'submitting'
  const submissionProgress = submissionStatus.total > 0
    ? Math.round((submissionStatus.submitted / submissionStatus.total) * 100)
    : 0

  return (
    <PageShell>
      <section className="container py-12 md:py-16">
        <div className="mx-auto min-w-0 max-w-2xl">
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
              Review
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-balance">Your entries</h1>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              Check each category, then confirm. Submissions are final.
            </p>

            <div className="mt-6 rounded-lg border border-border bg-muted/30 px-4 py-4">
              <p className="text-sm font-medium">Submit rules</p>
              <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-muted-foreground">
                <li>One prompt for each of the five categories.</li>
                <li>Each prompt must be {limitsLabel} (spaces at the ends are ignored).</li>
                <li>You cannot edit a prompt after you confirm and submit.</li>
              </ul>
            </div>

          {error ? (
            <div className="mt-6 flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
              <AlertCircle className="h-4 w-4" /> {error}
            </div>
          ) : null}

          {isSubmitting ? (
            <div className="mt-6 rounded-lg border border-border bg-card p-4">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">Submitting prompts individually…</span>
                <span className="text-muted-foreground tabular-nums">
                  {submissionStatus.submitted} / {submissionStatus.total}
                </span>
              </div>
              {submissionStatus.currentQuestion ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  Submitting: {submissionStatus.currentQuestion}
                </p>
              ) : null}
              <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full bg-primary transition-all duration-300"
                  style={{ width: `${submissionProgress}%` }}
                />
              </div>
            </div>
          ) : null}

          <div className="mt-8 space-y-5">
            {questions.map((q, idx) => {
              const text = draft[q.id] ?? ''
              const len = promptCharCount(text)
              const isSubmitted = submissionStatus.currentQuestion === q.title
              const isDone = submissionStatus.submitted > idx
              const inRange = isWithinPromptLimits(text)
              const brief = briefForQuestion(q.title, q.question_number)
              return (
                <Card
                  key={q.id}
                  className={cn(
                    isDone ? 'ring-1 ring-emerald-500/40' : '',
                    isSubmitted ? 'opacity-70' : '',
                  )}
                >
                  <CardContent className="min-w-0 pt-6">
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <h2 className="font-medium">
                        <span className="mr-2 text-muted-foreground">{idx + 1}.</span>
                        {q.title}
                      </h2>
                      <div className="flex items-center gap-2">
                        {isSubmitted ? <Spinner className="h-3.5 w-3.5" /> : null}
                        {isDone ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> : null}
                        <span className="text-xs tabular-nums text-muted-foreground">
                          {len} / {PROMPT_MAX_CHARS}
                        </span>
                      </div>
                    </div>
                    {brief ? (
                      <p className="mb-3 text-sm leading-relaxed text-muted-foreground">{brief}</p>
                    ) : q.description ? (
                      <p className="mb-3 text-sm text-muted-foreground">{q.description}</p>
                    ) : null}
                    <p className="min-w-0 overflow-hidden break-words whitespace-pre-wrap [overflow-wrap:anywhere] rounded-md bg-muted/40 p-4 text-sm leading-relaxed text-foreground">
                      {text || <span className="italic text-muted-foreground">(empty)</span>}
                    </p>
                    {!inRange && !isSubmitting ? (
                      <p className="mt-2 text-xs text-destructive">
                        {len < PROMPT_MIN_CHARS
                          ? `Below minimum length (${PROMPT_MIN_CHARS} characters). Please edit.`
                          : `Over the ${PROMPT_MAX_CHARS} character limit. Please edit.`}
                      </p>
                    ) : (
                      <p className="mt-2 text-xs text-muted-foreground">
                        {wordCount(text)} words · {promptLimitCopy()}
                      </p>
                    )}
                    <div className="mt-3 flex justify-end">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleEdit(q.id)}
                        disabled={isSubmitting}
                      >
                        <Pencil className="mr-1 h-3.5 w-3.5" /> Edit
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <Button variant="ghost" onClick={() => nav('/competition')} disabled={isSubmitting}>
              <ArrowLeft className="mr-1" /> Back to prompts
            </Button>
            <Button size="lg" onClick={handleSubmit} disabled={isSubmitting || !allReady}>
              {isSubmitting ? <Spinner className="h-4 w-4" /> : 'Confirm and submit'}
            </Button>
          </div>
          <p className="mt-4 text-center text-xs text-muted-foreground">
            Each prompt must be {limitsLabel}. This submission is final.
          </p>
        </div>
      </section>
    </PageShell>
  )
}
