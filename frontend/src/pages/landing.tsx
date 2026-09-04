import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { animate } from 'motion'
import { ArrowRight, Award, Sparkles, Zap, Trophy } from 'lucide-react'
import { PageShell } from '@/components/layout'
import QrLogin from '@/components/qr-login'
import { Button } from '@/components/ui/button'
import { FullScreenLoader } from '@/components/ui/spinner'
import { api } from '@/services/api'
import { useSession } from '@/store/session'
import type { Competition } from '@/types'

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  )
}

export default function LandingPage() {
  const [competition, setCompetition] = useState<Competition | null>(null)
  const [loading, setLoading] = useState(true)
  const [focusingLogin, setFocusingLogin] = useState(false)
  const token = useSession((s) => s.token)
  const nav = useNavigate()
  const location = useLocation()

  useEffect(() => {
    let active = true
    api
      .getActiveCompetition()
      .then((c) => active && setCompetition(c))
      .catch(() => active && setCompetition(null))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (loading) return
    const required = (location.state as { loginRequired?: boolean } | null)?.loginRequired
    if (!required) return

    const card = window.document.getElementById('participant-signin')
    if (!card) return

    window.history.replaceState({}, document.title)
    setFocusingLogin(true)
    card.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'center' })
    if (!prefersReducedMotion()) {
      animate(
        card,
        {
          boxShadow: [
            '0 0 0 0px rgba(16,185,129,0.0)',
            '0 0 0 5px rgba(16,185,129,0.35)',
            '0 0 0 0px rgba(16,185,129,0.0)',
          ],
        },
        { duration: 1.4, repeat: 3, repeatType: 'loop' },
      )
    }
    const t = window.setTimeout(() => setFocusingLogin(false), 3200)
    return () => window.clearTimeout(t)
  }, [loading, location.state])

  if (loading) return <PageShell><FullScreenLoader /></PageShell>

  return (
    <PageShell>
      {focusingLogin ? (
        <p className="mb-0 mt-4 text-center text-sm font-medium text-emerald-600">
          Please sign in with your QR code to continue.
        </p>
      ) : null}
      <section className="relative overflow-hidden border-b border-border/60">
        {/* Subtle grid, no decorative color orbs */}
        <div className="absolute inset-0 -z-10 dot-grid-fade opacity-40" />

        <div className="container relative py-20 md:py-32">
          <div className="max-w-3xl">
            <p className="mb-4 inline-flex items-center gap-1.5 rounded-full border border-border bg-background/60 backdrop-blur-sm px-3 py-1 text-xs font-medium text-muted-foreground animate-fade-in">
              <Award className="h-3.5 w-3.5" /> Generative AI · Prompt Engineering
            </p>
            <h1 className="text-balance text-5xl font-semibold leading-[1.05] tracking-tight md:text-6xl lg:text-7xl animate-fade-in-up font-display">
              Master Prompters 2.0
              <span className="block text-muted-foreground text-3xl md:text-4xl mt-2">Prompt Writing Competition</span>
            </h1>
            <p className="mt-6 max-w-xl text-base leading-relaxed text-muted-foreground animate-fade-in-up animation-delay-200">
              {competition?.description ??
                'Write five prompts, each judged independently. Sign in with your registration QR code to begin.'}
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3 animate-fade-in-up animation-delay-300">
              <Button
                size="lg"
                className="rounded-full"
                onClick={() => {
                  if (token) {
                    nav('/competition')
                  } else {
                    const el = document.getElementById('participant-signin')
                    el?.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'center' })
                  }
                }}
              >
                Go to competition <ArrowRight className="ml-1" />
              </Button>
              <Button asChild variant="outline" size="lg" className="rounded-full">
                <Link to="/leaderboard">View Leaderboard</Link>
              </Button>
            </div>

            {/* Feature cards */}
            <div className="mt-16 grid grid-cols-1 gap-4 sm:grid-cols-3 animate-fade-in-up animation-delay-500">
              <div className="rounded-xl border border-border bg-card p-4">
                <Sparkles className="h-5 w-5 text-primary" />
                <h3 className="mt-2 text-sm font-semibold">5 Categories</h3>
                <p className="mt-1 text-xs text-muted-foreground">Diverse creative challenges</p>
              </div>
              <div className="rounded-xl border border-border bg-card p-4">
                <Zap className="h-5 w-5 text-primary" />
                <h3 className="mt-2 text-sm font-semibold">Real-time Eval</h3>
                <p className="mt-1 text-xs text-muted-foreground">AI judges your prompts</p>
              </div>
              <div className="rounded-xl border border-border bg-card p-4">
                <Trophy className="h-5 w-5 text-primary" />
                <h3 className="mt-2 text-sm font-semibold">Win Prizes</h3>
                <p className="mt-1 text-xs text-muted-foreground">Top scorers get featured</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="relative container py-16 md:py-24">
        <div className="grid gap-10 md:grid-cols-2 md:items-center">
          <div className="animate-fade-in-up">
            <h2 className="text-3xl font-semibold tracking-tight font-display">
              {token ? 'Welcome back' : 'Sign in to participate'}
            </h2>
            <p className="mt-4 text-muted-foreground leading-relaxed">
              Use the QR code you received during registration. Once signed in you
              will answer five questions with a prompt each, review, and submit. Your
              responses cannot be edited after submission.
            </p>
            <div className="mt-6 space-y-2 text-sm text-muted-foreground">
              <div className="flex items-center gap-2">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">1</span>
                <span>Scan or paste your QR code</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">2</span>
                <span>Write 5 prompts across different categories</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">3</span>
                <span>Submit and get instant evaluation</span>
              </div>
            </div>
          </div>
          <div className="flex justify-center md:justify-end animate-fade-in-up animation-delay-200">
            <QrLogin competitionId={competition?.id ?? ''} />
          </div>
        </div>
      </section>
    </PageShell>
  )
}