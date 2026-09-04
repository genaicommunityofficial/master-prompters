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
    () => questions.length === 5 && questions.every((q) => (draft[q.id] ?? '').trim().length >= q.min_length),
    [questions, draft],
  )

  const handleSubmit = async () => {
    if (!competitionId) return
    if (!allReady) {
      setError('Every prompt must meet its minimum length before submitting.')
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
        // Some succeeded, some failed - try batch for remaining
        const failedQuestions = questions.filter((_q, idx) => !results[idx])
        const failedPrompts = failedQuestions.map((q) => ({
          question_id: q.id,
          prompt_text: draft[q.id] ?? '',
        }))

        if (failedPrompts.length > 0) {
          try {
            await api.submit(competitionId, failedPrompts)
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
        }

        window.localStorage.removeItem(DRAFT_KEY)
        nav('/submitted', { state: { message: 'Your responses have been submitted.' } })
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
        <div className="mx-auto max-w-2xl">
          <p className="text-sm font-medium tracking-wide text-muted-foreground uppercase">
            Competition · Review
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-balance">Review your prompts</h1>
          <p className="mt-3 text-muted-foreground">
            Make any final edits below, then submit. Once submitted, your responses cannot be changed.
          </p>

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
              const isSubmitted = submissionStatus.currentQuestion === q.title
              const isDone = submissionStatus.submitted > idx
              const tooShort = text.trim().length < q.min_length
              return (
                <Card
                  key={q.id}
                  className={cn(
                    isDone ? 'ring-1 ring-emerald-500/40' : '',
                    isSubmitted ? 'opacity-70' : '',
                  )}
                >
                  <CardContent className="pt-6">
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <h2 className="font-medium">
                        <span className="mr-2 text-muted-foreground">{idx + 1}.</span>
                        {q.title}
                      </h2>
                      <div className="flex items-center gap-2">
                        {isSubmitted ? <Spinner className="h-3.5 w-3.5" /> : null}
                        {isDone ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> : null}
                        <span className="text-xs text-muted-foreground">{wordCount(text)} words</span>
                      </div>
                    </div>
                    <p className="whitespace-pre-wrap rounded-md bg-muted/40 p-4 text-sm leading-relaxed text-foreground">
                      {text || <span className="italic text-muted-foreground">(empty)</span>}
                    </p>
                    {tooShort && !isSubmitting ? (
                      <p className="mt-2 text-xs text-destructive">
                        Below minimum length ({q.min_length} chars). Please edit.
                      </p>
                    ) : null}
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
            By submitting you confirm these are your final responses.
          </p>
        </div>
      </section>
    </PageShell>
  )
}
