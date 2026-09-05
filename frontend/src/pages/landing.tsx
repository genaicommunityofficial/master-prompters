import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { PageShell } from '@/components/layout'
import QrLogin from '@/components/qr-login'
import { TypeHeadline } from '@/components/type-line'
import { Button } from '@/components/ui/button'
import { FullScreenLoader } from '@/components/ui/spinner'
import { CATEGORIES } from '@/lib/categories'
import { CLUB_TAGLINE, COMMUNITY_LINE, COMPETITION_NAME } from '@/lib/brand'
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
    const t = window.setTimeout(() => setFocusingLogin(false), 2800)
    return () => window.clearTimeout(t)
  }, [loading, location.state])

  if (loading) return <PageShell><FullScreenLoader /></PageShell>

  return (
    <PageShell>
      {focusingLogin ? (
        <p className="mb-0 mt-4 text-center text-sm font-medium">
          Enter to continue.
        </p>
      ) : null}

      <section className="border-b border-border">
        <div className="container py-16 md:py-24">
          <div className="max-w-2xl">
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
              {COMMUNITY_LINE}
            </p>
            <TypeHeadline
              className="mt-4 font-pixel text-[clamp(1.35rem,5.2vw,2.75rem)] font-medium leading-none tracking-[0.06em]"
              text={COMPETITION_NAME}
            />
            <p className="mt-5 text-[15px] text-muted-foreground">{CLUB_TAGLINE}</p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button
                size="lg"
                onClick={() => {
                  if (token) {
                    nav('/competition')
                  } else {
                    document
                      .getElementById('participant-signin')
                      ?.scrollIntoView({
                        behavior: prefersReducedMotion() ? 'auto' : 'smooth',
                        block: 'center',
                      })
                  }
                }}
              >
                {token ? 'Continue' : 'Enter'}
              </Button>
              <Button asChild variant="outline" size="lg">
                <Link to="/leaderboard">Results</Link>
              </Button>
            </div>
          </div>
        </div>
      </section>

      <section className="border-b border-border">
        <div className="container py-14 md:py-16">
          <h2 className="text-sm font-medium tracking-[0.14em] uppercase text-muted-foreground">
            Categories
          </h2>
          <ol className="mt-8 divide-y divide-border border-y border-border">
            {CATEGORIES.map((c) => (
              <li key={c.n} className="grid gap-2 py-5 sm:grid-cols-[2.25rem_minmax(0,16rem)_1fr] sm:gap-6">
                <span className="text-xs tabular-nums text-muted-foreground">
                  {String(c.n).padStart(2, '0')}
                </span>
                <h3 className="text-sm font-medium leading-snug">{c.title}</h3>
                <p className="text-sm leading-relaxed text-muted-foreground">{c.brief}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="container py-16 md:py-20">
        <div className="mx-auto flex max-w-md justify-center">
          <QrLogin competitionId={competition?.id ?? ''} />
        </div>
      </section>
    </PageShell>
  )
}
