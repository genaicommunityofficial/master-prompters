import { useCallback, useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { Eye, EyeOff, RefreshCw } from 'lucide-react'
import { LeaderboardTable } from '@/components/leaderboard-table'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { api } from '@/services/api'
import type { LeaderboardResponse } from '@/types'
import { Banner } from './Banner'
import type { AdminOutletContext } from './context'
import { PageHeader } from './PageHeader'

const POLL_MS = 20_000

export default function AdminLeaderboardPage() {
  const { token, competitionId, testMode } = useOutletContext<AdminOutletContext>()
  const [data, setData] = useState<LeaderboardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [publishBusy, setPublishBusy] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')

  const refresh = useCallback(async (manual = false) => {
    if (manual) setBusy(true)
    try {
      const next = await api.adminLeaderboard(competitionId, token)
      setData(next)
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load the leaderboard.')
    } finally {
      setLoading(false)
      if (manual) setBusy(false)
    }
  }, [token, competitionId])

  useEffect(() => {
    void refresh()
    const id = window.setInterval(() => void refresh(), POLL_MS)
    return () => window.clearInterval(id)
  }, [refresh])

  const published = Boolean(data?.published)
  const entries = data?.entries ?? []

  const handleTogglePublish = async () => {
    setPublishBusy(true)
    try {
      if (published) {
        await api.adminUnpublishLeaderboard(competitionId, token)
        setNote('Leaderboard hidden from the public Results page.')
      } else {
        await api.adminPublishLeaderboard(competitionId, token)
        setNote('Leaderboard is now public on Results.')
      }
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not change leaderboard visibility.')
    } finally {
      setPublishBusy(false)
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        kicker={testMode ? 'Test dataset' : 'Live event'}
        title="Leaderboard"
        description="Current top fifty from completed evaluations. Public Results stay hidden until you publish."
      />
      <Banner message={error} onDismiss={() => setError('')} />
      <Banner message={note} onDismiss={() => setNote('')} tone="note" />

      <p className="text-sm text-muted-foreground" role="status">
        {published ? 'Published on the public Results page.' : 'Preview only — not published.'}
        {entries.length ? ` · ${entries.length} ranked` : ''}
      </p>

      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" variant="outline" onClick={() => void refresh(true)} disabled={busy}>
          {busy ? <Spinner className="h-4 w-4" /> : <RefreshCw className="h-4 w-4" />} Refresh
        </Button>
        <Button
          size="sm"
          variant={published ? 'outline' : 'default'}
          onClick={() => void handleTogglePublish()}
          disabled={publishBusy || loading}
        >
          {publishBusy ? <Spinner className="h-4 w-4" /> : published ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          {published ? 'Unpublish' : 'Publish'}
        </Button>
      </div>

      {loading && !data ? (
        <p className="text-sm text-muted-foreground">Loading standings…</p>
      ) : (
        <LeaderboardTable
          entries={entries}
          emptyLabel="No completed evaluations yet. Rankings appear here as Gemini scores prompts."
        />
      )}
    </div>
  )
}
