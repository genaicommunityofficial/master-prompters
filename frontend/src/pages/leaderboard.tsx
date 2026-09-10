import { useEffect, useState } from 'react'
import { useSession } from '@/store/session'
import { PageShell } from '@/components/layout'
import { FullScreenLoader } from '@/components/ui/spinner'
import { api } from '@/services/api'
import type { LeaderboardResponse } from '@/types'
import { COMPETITION_NAME } from '@/lib/brand'
import { LeaderboardTable } from '@/components/leaderboard-table'

export default function LeaderboardPage() {
  const competitionId = useSession((s) => s.competitionId)
  const [data, setData] = useState<LeaderboardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        const id = competitionId || (await api.getActiveCompetition()).id
        const d = await api.leaderboard(id)
        if (!active) return
        setData(d)
        setError('')
      } catch {
        if (!active) return
        setData(null)
        setError('Could not load the leaderboard. Please try again.')
      } finally {
        if (active) setLoading(false)
      }
    }
    void load()
    return () => {
      active = false
    }
  }, [competitionId])

  if (loading) return <PageShell><FullScreenLoader label="Loading leaderboard" /></PageShell>

  const visible = data?.visible ?? false

  return (
    <PageShell>
      <section className="container py-12 md:py-16">
        <div className="mx-auto max-w-5xl">
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            {COMPETITION_NAME}
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">Results</h1>

          {error ? (
            <div className="mt-8 rounded-xl border border-destructive/30 bg-destructive/5 p-10 text-center">
              <p className="text-lg font-medium text-destructive">{error}</p>
            </div>
          ) : !visible ? (
            <div className="mt-8 rounded-xl border border-border bg-muted/40 p-10 text-center">
              <p className="text-lg font-medium">Not published yet</p>
            </div>
          ) : (
            <>
              <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-muted-foreground">
                Congratulations to everyone who made the top fifty.
              </p>
              <div className="mt-8">
                <LeaderboardTable
                  entries={data?.entries ?? []}
                  emptyLabel="No results published yet."
                />
              </div>
            </>
          )}
        </div>
      </section>
    </PageShell>
  )
}
