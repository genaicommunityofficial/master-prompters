import { useEffect, useState } from 'react'
import { useSession } from '@/store/session'
import { PageShell } from '@/components/layout'
import { Card, CardContent } from '@/components/ui/card'
import { FullScreenLoader } from '@/components/ui/spinner'
import { api } from '@/services/api'
import type { LeaderboardResponse } from '@/types'
import { cn } from '@/lib/utils'

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
        <div className="mx-auto max-w-2xl">
          <p className="text-sm font-medium tracking-wide text-muted-foreground uppercase">
            Public
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">Leaderboard</h1>

          {error ? (
            <div className="mt-8 rounded-xl border border-destructive/30 bg-destructive/5 p-10 text-center">
              <p className="text-lg font-medium text-destructive">{error}</p>
            </div>
          ) : !visible ? (
            <div className="mt-8 rounded-xl border border-border bg-muted/40 p-10 text-center">
              <p className="text-lg font-medium">Results will be published later</p>
              <p className="mt-2 text-sm text-muted-foreground">
                The leaderboard is currently hidden.
              </p>
            </div>
          ) : (
            <>
              <p className="mt-3 text-muted-foreground">
                Rankings are shown only for fully evaluated submissions.
              </p>
              <Card className="mt-8">
                <CardContent className="p-0">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-muted-foreground">
                        <th className="px-5 py-3 font-medium">Rank</th>
                        <th className="px-5 py-3 font-medium">Participant</th>
                        <th className="px-5 py-3 text-right font-medium">Score</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(data?.entries ?? []).map((e, i) => (
                        <tr
                          key={`${e.rank}-${i}`}
                          className={cn(
                            'border-b border-border/60 last:border-0',
                            i <= 2 ? 'bg-muted/30' : '',
                          )}
                        >
                          <td className="px-5 py-3.5 font-semibold">{e.rank}</td>
                          <td className="px-5 py-3.5">{e.display_name}</td>
                          <td className="px-5 py-3.5 text-right font-semibold tabular-nums">
                            {e.total_score}
                          </td>
                        </tr>
                      ))}
                      {data?.entries.length === 0 ? (
                        <tr>
                          <td colSpan={3} className="px-5 py-8 text-center text-muted-foreground">
                            No results published yet.
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            </>
          )}
        </div>
      </section>
    </PageShell>
  )
}