import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, ArrowRight, Save, Check } from 'lucide-react'
import { PageShell } from '@/components/layout'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { FullScreenLoader } from '@/components/ui/spinner'
import { api } from '@/services/api'
import { useSession } from '@/store/session'
import type { Question } from '@/types'
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
    api
      .submissionExists()
      .then((ex) => {
        if (ex.submitted) {
          nav('/submitted', { replace: true })
          return
        }
        return api.getCompetition(competitionId)
      })
      .then((c) => {
        if (c && 'questions' in c) setQuestions(c.questions)
      })
      .catch(() => setError('Could not load the competition questions.'))
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

  const setAnswer = (id: string, value: string) => {
    persist({ ...draft, [id]: value })
  }

  const allValid = useMemo(
    () =>
      questions.length === 5 &&
      questions.every((q) => (draft[q.id] ?? '').trim().length >= q.min_length),
    [questions, draft],
  )

  const handleSaveFlash = () => {
    setSavedFlash(true)
    window.setTimeout(() => setSavedFlash(false), 1500)
  }

  if (loading) return <PageShell><FullScreenLoader label="Loading competition" /></PageShell>

  return (
    <PageShell>
      <section className="relative container py-12 md:py-16">
        {/* Background decoration */}
        <div className="absolute inset-0 -z-10 dot-grid opacity-20" />
        <div className="mx-auto max-w-2xl">
          <div className="mb-8">
            <p className="text-sm font-medium tracking-wide text-muted-foreground uppercase">
              Competition
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-balance">
              Write your five prompts
            </h1>
            <p className="mt-3 text-muted-foreground leading-relaxed">
              Answer each question with a prompt. You can edit your answers on the review page before submitting.
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
              const len = value.trim().length
              const met = len >= q.min_length
              return (
                <Card
                  key={q.id}
                  className={cn(
                    'transition-all duration-300 card-hover animate-fade-in',
                    met ? 'ring-1 ring-primary/20' : '',
                  )}
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
                    {q.description ? (
                      <p className="text-sm text-muted-foreground">{q.description}</p>
                    ) : null}
                    <Textarea
                      id={q.id}
                      value={value}
                      rows={6}
                      maxLength={q.max_length}
                      placeholder={`Your prompt for ${q.title}…`}
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
                        {met ? 'Ready' : `Minimum ${q.min_length} characters`}
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
              Review & submit <ArrowRight className="ml-1" />
            </Button>
          </div>
          {!allValid ? (
            <p className="mt-3 text-center text-xs text-muted-foreground">
              Complete all five prompts (minimum length each) to continue.
            </p>
          ) : null}
        </div>
      </section>
    </PageShell>
  )
}
