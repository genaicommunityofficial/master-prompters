import { useCallback, useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { Eye, EyeOff, Lock, LockOpen, Play, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { api } from '@/services/api'
import type { DashboardMetrics, EvalProgress, ParticipantRoster } from '@/types'
import { Banner } from './Banner'
import type { AdminOutletContext } from './context'
import { EvalProgressPanel } from './EvalProgressPanel'
import { PageHeader } from './PageHeader'
import { Stat } from './Stat'

export default function DashboardPage() {
  const { token, competitionId, testMode } = useOutletContext<AdminOutletContext>()
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null)
  const [evalStatus, setEvalStatus] = useState<EvalProgress | null>(null)
  const [roster, setRoster] = useState<ParticipantRoster | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [evalBusy, setEvalBusy] = useState(false)
  const [statusBusy, setStatusBusy] = useState(false)
  const [leaderboardBusy, setLeaderboardBusy] = useState(false)
  const [leaderboardVisible, setLeaderboardVisible] = useState<boolean | null>(null)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')

  const refresh = useCallback(async () => {
    setBusy(true)
    try {
      const [dash, status, people] = await Promise.all([
        api.adminDashboard(competitionId, token),
        api.adminEvalStatus(competitionId, token),
        api.adminParticipants(competitionId, token).catch(() => null),
      ])
      setMetrics(dash.metrics)
      setEvalStatus(status)
      setRoster(people)
      setLeaderboardVisible(status.leaderboard_visible)
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load dashboard.')
    } finally {
      setLoading(false)
      setBusy(false)
    }
  }, [token, competitionId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const handleStartEval = async () => {
    setEvalBusy(true)
    try {
      const res = await api.adminStartEval(
        { competition_id: competitionId, batch_size: 8, concurrency: 4, max_retries: 3 },
        token,
      )
      setNote(
        res.accepted === false
          ? 'An evaluation run is already in progress.'
          : `Evaluation started for ${testMode ? 'test' : 'live'} with Gemini.`,
      )
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start evaluation.')
    } finally {
      setEvalBusy(false)
    }
  }

  const handleToggleStatus = async () => {
    const opening = metrics?.competition_status !== 'OPEN'
    if (!opening && !window.confirm('Close submissions? New logins and submissions will be rejected.')) {
      return
    }
    setStatusBusy(true)
    try {
      if (opening) {
        await api.adminOpenCompetition(competitionId, token)
        setNote('Submissions reopened.')
      } else {
        await api.adminCloseCompetition(competitionId, token)
        setNote('Submissions closed.')
      }
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not update competition status.')
    } finally {
      setStatusBusy(false)
    }
  }

  const handleToggleLeaderboard = async () => {
    setLeaderboardBusy(true)
    try {
      if (leaderboardVisible) {
        await api.adminUnpublishLeaderboard(competitionId, token)
        setLeaderboardVisible(false)
      } else {
        await api.adminPublishLeaderboard(competitionId, token)
        setLeaderboardVisible(true)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to toggle leaderboard.')
    } finally {
      setLeaderboardBusy(false)
    }
  }

  if (loading && !metrics) {
    return (
      <div className="flex items-center gap-3 py-16 text-sm text-muted-foreground">
        <Spinner className="h-4 w-4" /> Loading dashboard…
      </div>
    )
  }

  if (!metrics) {
    return (
      <div className="mx-auto max-w-md rounded-lg border border-destructive/30 bg-destructive/5 p-6 text-sm">
        <p className="font-medium text-destructive" role="alert">
          {error || 'Could not load the admin dashboard.'}
        </p>
        <Button className="mt-4" variant="outline" onClick={() => void refresh()}>
          Try again
        </Button>
      </div>
    )
  }

  const running = evalStatus?.run?.status === 'running'
  const open = metrics.competition_status === 'OPEN'

  return (
    <div className="space-y-8">
      <PageHeader
        kicker={testMode ? 'Test dataset' : 'Live event'}
        title="Dashboard"
        description={
          testMode
            ? 'Same control surface as live, scoped to the 1500-prompt test set.'
            : 'Open/close submissions, run eval, and publish the leaderboard.'
        }
      />
      <Banner message={error} onDismiss={() => setError('')} />
      <Banner message={note} onDismiss={() => setNote('')} tone="note" />

      <p className="text-sm text-muted-foreground">
        <span className="font-medium text-foreground">{open ? 'Open' : metrics.competition_status}</span>
        {' · '}
        {running ? 'eval running' : 'eval idle'}
        {' · '}
        {evalStatus ? `${evalStatus.totals.progress_pct.toFixed(0)}% scored` : '—'}
        {' · '}
        leaderboard {leaderboardVisible ? 'published' : 'hidden'}
      </p>

      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" variant="outline" onClick={() => void refresh()} disabled={busy}>
          {busy ? <Spinner className="h-4 w-4" /> : <RefreshCw className="h-4 w-4" />} Refresh
        </Button>
        <Button
          size="sm"
          variant={open ? 'outline' : 'default'}
          onClick={() => void handleToggleStatus()}
          disabled={statusBusy}
        >
          {open ? (
            <>
              <Lock className="h-4 w-4" /> Close submissions
            </>
          ) : (
            <>
              <LockOpen className="h-4 w-4" /> Open submissions
            </>
          )}
        </Button>
        <Button size="sm" onClick={() => void handleStartEval()} disabled={evalBusy || running}>
          {evalBusy || running ? <Spinner className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          {running ? 'Evaluating…' : 'Start eval'}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => void handleToggleLeaderboard()}
          disabled={leaderboardBusy}
        >
          {leaderboardVisible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          {leaderboardVisible ? 'Unpublish leaderboard' : 'Publish leaderboard'}
        </Button>
      </div>

      <div className={`grid gap-4 sm:grid-cols-2 ${testMode ? 'lg:grid-cols-3' : 'lg:grid-cols-4'}`}>
        <Stat label="Registered" value={roster?.registered ?? metrics.total_participants} />
        {testMode ? null : <Stat label="Logged in" value={roster?.logged_in ?? '—'} />}
        <Stat label="Submitted" value={roster?.submitted ?? metrics.submitted} />
        <Stat label="Evaluated" value={metrics.evaluated} />
      </div>

      <EvalProgressPanel status={evalStatus} title="Evaluation" compact />
    </div>
  )
}
