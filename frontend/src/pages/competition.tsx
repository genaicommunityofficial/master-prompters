import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, ArrowRight, Save, Check } from 'lucide-react'
import { PageShell } from '@/components/layout'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { FullScreenLoader } from '@/components/ui/spinner'
import { api, ApiError } from '@/services/api'
import { useSession } from '@/store/session'
import type { Question } from '@/types'
import { briefForQuestion } from '@/lib/categories'
import { COMPETITION_NAME } from '@/lib/brand'
import {
  isWithinPromptLimits,
  promptCharCount,
  promptLengthHint,
  promptLimitCopy,
} from '@/lib/promptLimits'
import { cn, wordCount } from '@/lib/utils'

const DRAFT_KEY = 'pc_draft_v2'

interface Draft {
  [questionId: string]: string
}

export default function CompetitionPage() {
  const nav = useNavigate()
  const competitionId = useSession((s) => s.competitionId)
  const token = useSession((s) => s.token)

  const [questions, setQuestions] = useState<Question[]>([])
  const [loading, setLoading] = useState(true)
  const [draft, setDraft] = useState<Draft>({})
  const [savedFlash, setSavedFlash] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!token || !competitionId) {
      setLoading(false)
      nav('/', { replace: true, state: { loginRequired: true } })
      return
    }
    const saved: Draft = (() => {
      try {
        return JSON.parse(window.localStorage.getItem(DRAFT_KEY) ?? '{}') as Draft
      } catch {
        return {}
      }
    })()
    setDraft(saved)
    let redirected = false
    api
      .submissionExists()
      .then((ex) => {
        if (ex.submitted) {
          redirected = true
          nav('/submitted', { replace: true })
        }
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) {
          redirected = true
          nav('/', { replace: true, state: { loginRequired: true } })
          return
        }
        setError(e instanceof Error ? e.message : 'Could not check submission status.')
      })
      .then(() => {
        if (redirected) return
        return api.getCompetition(competitionId)
      })
      .then((c) => {
        if (c && 'questions' in c) setQuestions(c.questions)
      })
      .catch((e) => {
        if (redirected) return
        setError(e instanceof Error ? e.message : 'Could not load the competition questions.')
      })
      .finally(() => setLoading(false))
  }, [token, competitionId, nav])

  useEffect(() => {
    if (loading || questions.length === 0) return
    const focusId = window.sessionStorage.getItem('pc_edit_focus')
    if (!focusId) return
    window.sessionStorage.removeItem('pc_edit_focus')
    const el = window.document.getElementById(focusId)
    el?.scrollIntoView({ block: 'center' })
    el?.focus()
  }, [loading, questions])

  const persist = (next: Draft) => {
    setDraft(next)
    window.localStorage.setItem(DRAFT_KEY, JSON.stringify(next))
  }

  useEffect(() => {
    if (questions.length === 0) return
    setDraft((current) => {
      let changed = false
      const next = { ...current }
      for (const q of questions) {
        const value = next[q.id]
        if (typeof value === 'string' && value.length > q.max_length) {
          next[q.id] = value.slice(0, q.max_length)
          changed = true
        }
      }
      if (!changed) return current
      window.localStorage.setItem(DRAFT_KEY, JSON.stringify(next))
      return next
    })
  }, [questions])

  const setAnswer = (id: string, value: string) => {
    const question = questions.find((item) => item.id === id)
    persist({ ...draft, [id]: question ? value.slice(0, question.max_length) : value })
  }

  const allValid = useMemo(
    () =>
      questions.length === 5 &&
      questions.every((q) => isWithinPromptLimits(draft[q.id] ?? '', q.min_length, q.max_length)),
    [questions, draft],
  )

  const limitsLabel = useMemo(() => {
    const first = questions[0]
    return promptLimitCopy(first?.min_length, first?.max_length)
  }, [questions])

  const handleSaveFlash = () => {
    setSavedFlash(true)
    window.setTimeout(() => setSavedFlash(false), 1500)
  }

  if (loading) return <PageShell><FullScreenLoader label="Loading competition" /></PageShell>

  return (
    <PageShell>
      <section className="container py-12 md:py-16">
        <div className="mx-auto max-w-2xl">
          <div className="mb-8">
            <h1 className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
              {COMPETITION_NAME}
            </h1>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              Five categories. Each prompt must be {limitsLabel}. Write a complete instruction
              for that category, then continue to review.
            </p>
          </div>

          {error ? (
            <div className="mb-6 flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
              <AlertCircle className="h-4 w-4" /> {error}
            </div>
          ) : null}

          <div className="space-y-6">
            {questions.map((q, idx) => {
              const value = draft[q.id] ?? ''
              const len = promptCharCount(value)
              const met = isWithinPromptLimits(value, q.min_length, q.max_length)
              const brief = briefForQuestion(q.title, q.question_number)
              return (
                <Card
                  key={q.id}
                  className={cn(met ? 'ring-1 ring-foreground/15' : '')}
                >
                  <CardContent className="space-y-3 pt-6">
                    <div className="flex items-baseline justify-between gap-3">
                      <Label htmlFor={q.id} className="text-base">
                        <span className="mr-2 text-muted-foreground">{idx + 1}.</span>
                        {q.title}
                      </Label>
                      <span className="text-xs text-muted-foreground tabular-nums">
                        {len} / {q.max_length}
                      </span>
                    </div>
                    {brief ? (
                      <p className="text-sm leading-relaxed text-muted-foreground">{brief}</p>
                    ) : q.description ? (
                      <p className="text-sm text-muted-foreground">{q.description}</p>
                    ) : null}
                    <Textarea
                      id={q.id}
                      value={value}
                      rows={6}
                      maxLength={q.max_length}
                      placeholder=""
                      onChange={(e) => setAnswer(q.id, e.target.value)}
                    />
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">{wordCount(value)} words</span>
                      <span
                        className={cn(
                          'font-medium',
                          met ? 'text-primary' : 'text-muted-foreground',
                        )}
                      >
                        {promptLengthHint(len, q.min_length, q.max_length)}
                      </span>
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <Button variant="ghost" onClick={handleSaveFlash}>
              {savedFlash ? 'Saved' : 'Save draft'}
              {savedFlash ? <Check className="h-4 w-4" /> : <Save className="h-4 w-4" />}
            </Button>
            <Button
              size="lg"
              onClick={() => nav('/competition/review')}
              disabled={!allValid}
            >
              Continue <ArrowRight className="ml-1" />
            </Button>
          </div>
        </div>
      </section>
    </PageShell>
  )
}
