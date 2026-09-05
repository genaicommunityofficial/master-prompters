import { useCallback, useEffect, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { Pause, Play, RefreshCw, RotateCcw, RotateCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
import { api } from '@/services/api'
import type { EvalLogEntry, EvalProgress, EvalRunStatus, LiveLogsResponse } from '@/types'
import { Banner } from './Banner'
import type { AdminOutletContext } from './context'
import { EvalProgressPanel } from './EvalProgressPanel'
import { PageHeader } from './PageHeader'
import { EVAL_BATCH_SIZE, EVAL_CONCURRENCY, EVAL_MAX_RETRIES } from './constants'

function formatLogTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString(undefined, { hour12: false })
}

export default function EvalPage() {
  const { token, competitionId, testMode } = useOutletContext<AdminOutletContext>()
  const [status, setStatus] = useState<EvalProgress | null>(null)
  const [run, setRun] = useState<EvalRunStatus | null>(null)
  const [logs, setLogs] = useState<EvalLogEntry[]>([])
  const [live, setLive] = useState<LiveLogsResponse | null>(null)
  const seq = useRef(0)
  const logListRef = useRef<HTMLUListElement>(null)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [evalBusy, setEvalBusy] = useState(false)

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await api.adminEvalStatus(competitionId, token))
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load evaluation status.')
    }
  }, [token, competitionId])

  const refreshLogs = useCallback(async () => {
    try {
      const payload = await api.adminEvalLogs(seq.current, token)
      if (payload.run.competition_id && payload.run.competition_id !== competitionId) {
        return
      }
      setRun(payload.run)
      if (payload.logs.length) {
        setLogs((prev) => {
          const seen = new Set(prev.map((l) => l.seq))
          const next = [...prev]
          for (const row of payload.logs) {
            if (!seen.has(row.seq)) next.push(row)
          }
          return next.slice(-500)
        })
        seq.current = Math.max(seq.current, ...payload.logs.map((l) => l.seq))
      }
    } catch {
      /* keep last snapshot */
    }
  }, [token, competitionId])

  const refresh = useCallback(async () => {
    setBusy(true)
    await Promise.all([
      refreshStatus(),
      refreshLogs(),
      api.adminLiveLogs(undefined, token).then(setLive).catch(() => undefined),
    ])
    setBusy(false)
  }, [refreshStatus, refreshLogs, token])

  useEffect(() => {
    seq.current = 0
    setLogs([])
    void refresh()
  }, [refresh])

  const runStatus = run?.status ?? status?.run?.status ?? 'idle'
  const active = runStatus === 'running' || runStatus === 'pausing'

  useEffect(() => {
    if (!active && runStatus !== 'paused') return
    const id = window.setInterval(() => {
      void refreshStatus()
      void refreshLogs()
    }, 1000)
    return () => window.clearInterval(id)
  }, [active, runStatus, refreshStatus, refreshLogs])

  useEffect(() => {
    const el = logListRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [logs])

  const startParams = {
    competition_id: competitionId,
    batch_size: EVAL_BATCH_SIZE,
    concurrency: EVAL_CONCURRENCY,
    max_retries: EVAL_MAX_RETRIES,
  }

  const handleStart = async (mode: 'restart' | 'resume' | 'retry_failed') => {
    if (mode === 'restart' && testMode) {
      if (
        !window.confirm(
          'Restart from the beginning? This clears test scores and scores every prompt again.',
        )
      ) {
        return
      }
    }
    setEvalBusy(true)
    try {
      const res = await api.adminStartEval({ ...startParams, mode }, token)
      setRun(res)
      const rejected = res.accepted === false
      setNote(
        rejected
          ? 'An evaluation run is already in progress. Pause it first.'
          : mode === 'retry_failed'
            ? 'Retrying failed jobs with the current Gemini model.'
            : mode === 'resume'
              ? 'Resuming from where the run left off.'
              : testMode
                ? 'Test evaluation restarted from the beginning. Watch the log for each prompt.'
                : 'Live evaluation started. Already-scored prompts are skipped.',
      )
      if (!rejected && mode === 'restart') {
        setLogs([])
        seq.current = 0
      }
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start evaluation.')
    } finally {
      setEvalBusy(false)
    }
  }

  const handlePause = async () => {
    setEvalBusy(true)
    try {
      const res = await api.adminPauseEval(token)
      setRun(res)
      setNote(
        res.accepted === false
          ? 'Nothing to pause. Start or resume a run first.'
          : 'Pausing after the current batch. Resume to continue, or retry failed jobs.',
      )
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not pause evaluation.')
    } finally {
      setEvalBusy(false)
    }
  }

  const scored = run?.processed ?? 0
  const total = run?.enqueued ?? 0
  const failed = run?.failed ?? status?.totals.job_failed ?? 0
  const paused = runStatus === 'paused'
  const pausing = runStatus === 'pausing'

  return (
    <div className="space-y-8">
      <PageHeader
        kicker={testMode ? 'Test dataset' : 'Live competition'}
        title="Evaluation"
        description="Pause to stop after the current batch. Resume continues remaining prompts. Retry failed only re-scores jobs that failed. Restart test eval from the beginning."
      />
      <Banner message={error} onDismiss={() => setError('')} />
      <Banner message={note} onDismiss={() => setNote('')} tone="note" />

      <div className="flex flex-wrap gap-3">
        {active ? (
          <Button onClick={() => void handlePause()} disabled={evalBusy || pausing}>
            {evalBusy || pausing ? <Spinner className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
            {pausing ? 'Pausing…' : 'Pause'}
          </Button>
        ) : (
          <Button onClick={() => void handleStart('resume')} disabled={evalBusy}>
            {evalBusy ? <Spinner className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            {paused ? 'Resume' : 'Continue remaining'}
          </Button>
        )}
        <Button
          variant="outline"
          onClick={() => void handleStart('retry_failed')}
          disabled={evalBusy || active}
        >
          {evalBusy ? <Spinner className="h-4 w-4" /> : <RotateCw className="h-4 w-4" />}
          Retry failed
        </Button>
        <Button
          variant="outline"
          onClick={() => void handleStart('restart')}
          disabled={evalBusy || active}
        >
          {evalBusy ? <Spinner className="h-4 w-4" /> : <RotateCcw className="h-4 w-4" />}
          {testMode ? 'Restart from start' : 'Start remaining'}
        </Button>
        <Button size="sm" variant="outline" onClick={() => void refresh()} disabled={busy}>
          {busy ? <Spinner className="h-4 w-4" /> : <RefreshCw className="h-4 w-4" />} Refresh
        </Button>
      </div>

      <EvalProgressPanel status={status} title="Pipeline">
        <Card className="mt-6">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Live log</CardTitle>
            <p className="text-sm text-muted-foreground">
              {runStatus === 'running'
                ? total
                  ? `${scored} / ${total} this run · ${failed} failed`
                  : 'Starting…'
                : pausing
                  ? 'Pausing after this batch…'
                  : paused
                    ? `Paused · ${failed} failed. Resume or retry failed.`
                    : logs.length
                      ? `${scored} scored this run · ${failed} failed`
                      : 'Start a run to stream progress.'}
            </p>
          </CardHeader>
          <CardContent>
            {logs.length === 0 ? (
              <p className="text-sm text-muted-foreground">No eval logs yet.</p>
            ) : (
              <ul
                ref={logListRef}
                className="max-h-80 space-y-1 overflow-auto font-mono text-xs"
                aria-live="polite"
              >
                {logs.map((l) => (
                  <li
                    key={l.seq}
                    className={l.level === 'error' ? 'text-destructive' : 'text-muted-foreground'}
                  >
                    <span className="tabular-nums text-muted-foreground/80">{formatLogTime(l.ts)}</span>
                    {'  '}
                    {l.message}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <details className="mt-4">
          <summary className="cursor-pointer text-sm font-medium text-muted-foreground">
            Request monitor
            {live ? ` · ${live.stats.requests_last_60s} req / 60s` : ''}
          </summary>
          <Card className="mt-3">
            <CardHeader>
              <CardTitle className="text-base">Recent HTTP</CardTitle>
            </CardHeader>
            <CardContent>
              {!live || live.logs.length === 0 ? (
                <p className="text-sm text-muted-foreground">No requests logged yet.</p>
              ) : (
                <div className="max-h-64 overflow-auto">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-background text-left text-xs uppercase text-muted-foreground">
                      <tr className="border-b border-border">
                        <th className="px-2 py-2 font-medium">When</th>
                        <th className="px-2 py-2 font-medium">Method</th>
                        <th className="px-2 py-2 font-medium">Path</th>
                        <th className="px-2 py-2 font-medium">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {live.logs.slice(0, 40).map((row) => (
                        <tr key={row.id} className="border-b border-border/60">
                          <td className="px-2 py-1.5 tabular-nums text-muted-foreground">
                            {row.created_at?.slice(11, 19) ?? '-'}
                          </td>
                          <td className="px-2 py-1.5">{row.method}</td>
                          <td className="px-2 py-1.5 font-mono text-xs">{row.path}</td>
                          <td className="px-2 py-1.5 tabular-nums">{row.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </details>
      </EvalProgressPanel>
    </div>
  )
}
