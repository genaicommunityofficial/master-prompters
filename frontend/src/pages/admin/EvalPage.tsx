import { useCallback, useEffect, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { Play, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
import { api } from '@/services/api'
import type { EvalLogEntry, EvalProgress, EvalRunStatus, LiveLogsResponse } from '@/types'
import { Banner } from './Banner'
import type { AdminOutletContext } from './context'
import { EvalProgressPanel } from './EvalProgressPanel'
import { PageHeader } from './PageHeader'

export default function EvalPage() {
  const { token, competitionId, testMode } = useOutletContext<AdminOutletContext>()
  const [status, setStatus] = useState<EvalProgress | null>(null)
  const [run, setRun] = useState<EvalRunStatus | null>(null)
  const [logs, setLogs] = useState<EvalLogEntry[]>([])
  const [live, setLive] = useState<LiveLogsResponse | null>(null)
  const seq = useRef(0)
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
          return next.slice(-300)
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

  useEffect(() => {
    if (run?.status !== 'running' && status?.run?.status !== 'running') return
    const id = window.setInterval(() => {
      void refreshStatus()
      void refreshLogs()
    }, 1500)
    return () => window.clearInterval(id)
  }, [run?.status, status?.run?.status, refreshStatus, refreshLogs])

  const handleStart = async () => {
    setEvalBusy(true)
    try {
      const res = await api.adminStartEval(
        { competition_id: competitionId, batch_size: 8, concurrency: 4, max_retries: 3 },
        token,
      )
      setRun(res)
      setNote(
        res.accepted === false
          ? 'An evaluation run is already in progress.'
          : `${testMode ? 'Test' : 'Live'} evaluation started with Gemini.`,
      )
      if (res.accepted !== false) {
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

  const running = run?.status === 'running' || status?.run?.status === 'running'

  return (
    <div className="space-y-8">
      <PageHeader
        kicker={testMode ? 'Test dataset' : 'Live competition'}
        title="Evaluation"
        description="Gemini scoring, per-category progress, cost, and request traffic."
      />
      <Banner message={error} onDismiss={() => setError('')} />
      <Banner message={note} onDismiss={() => setNote('')} tone="note" />

      <div className="flex flex-wrap gap-3">
        <Button onClick={() => void handleStart()} disabled={evalBusy || running}>
          {evalBusy || running ? <Spinner className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          {running ? 'Evaluating…' : 'Start Gemini eval'}
        </Button>
        <Button size="sm" variant="outline" onClick={() => void refresh()} disabled={busy}>
          {busy ? <Spinner className="h-4 w-4" /> : <RefreshCw className="h-4 w-4" />} Refresh
        </Button>
      </div>

      <EvalProgressPanel status={status} title="Pipeline">
        <details className="mt-6">
          <summary className="cursor-pointer text-sm font-medium text-muted-foreground">Eval log</summary>
          <Card className="mt-3">
            <CardContent className="pt-4">
              {logs.length === 0 ? (
                <p className="text-sm text-muted-foreground">No eval logs yet. Start a run to stream progress.</p>
              ) : (
                <ul className="max-h-72 space-y-1 overflow-auto font-mono text-xs">
                  {logs.map((l) => (
                    <li key={l.seq} className="text-muted-foreground">
                      <span className="tabular-nums">{l.seq}</span> {l.level} {l.message}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </details>

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
                            {row.created_at?.slice(11, 19) ?? '—'}
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
