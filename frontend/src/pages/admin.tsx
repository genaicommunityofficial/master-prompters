import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  Download,
  Eye,
  EyeOff,
  FileText,
  Gauge,
  Lock,
  LockOpen,
  Play,
  RefreshCw,
  ShieldCheck,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { AdminShell } from '@/components/layout'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Spinner } from '@/components/ui/spinner'
import {
  api,
  clearAdminSession,
  getAdminToken,
  setAdminToken,
} from '@/services/api'
import type {
  Analytics,
  CleanupResult,
  CriteriaEntry,
  DashboardMetrics,
  EvalLogEntry,
  EvalRunStatus,
  LiveLogsResponse,
  StressStatus,
} from '@/types'

type Tab = 'dashboard' | 'monitor' | 'cost' | 'criteria' | 'export' | 'stress'

const API_BASE: string = (import.meta.env.VITE_API_BASE_URL as string) ?? '/api'

function Stat({ label, value }: { label: string; value: number | string | null | undefined }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="text-2xl font-semibold tabular-nums">{value ?? '—'}</div>
      <div className="mt-1 text-xs text-muted-foreground">{label}</div>
    </div>
  )
}

export default function AdminPage() {
  const [adminToken, setAdminTokenState] = useState<string | null>(getAdminToken())
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loginError, setLoginError] = useState('')
  const [phase, setPhase] = useState<Tab>('dashboard')
  const [error, setError] = useState('')

  // Dashboard
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null)
  const [loading, setLoading] = useState(false)
  const [evalBusy, setEvalBusy] = useState(false)
  const [queueNote, setQueueNote] = useState('')
  const [evalRun, setEvalRun] = useState<EvalRunStatus | null>(null)
  const [evalLogs, setEvalLogs] = useState<EvalLogEntry[]>([])
  const evalLogSeq = useRef(0)
  const [leaderboardVisible, setLeaderboardVisible] = useState<boolean | null>(null)
  const [leaderboardBusy, setLeaderboardBusy] = useState(false)
  const [statusBusy, setStatusBusy] = useState(false)
  const [dashBusy, setDashBusy] = useState(false)

  // Monitor
  const [live, setLive] = useState<LiveLogsResponse | null>(null)
  const pollRef = useRef<number | null>(null)

  // Cost / analytics
  const [analytics, setAnalytics] = useState<Analytics | null>(null)

  // Export
  const [exportNote, setExportNote] = useState('')

  const token = adminToken

  const refreshDashboard = useCallback(async () => {
    if (!token) return
    setDashBusy(true)
    try {
      const d = await api.adminDashboard(token)
      setMetrics(d.metrics)
      setError('')
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Could not load dashboard.'
      setMetrics((current) => {
        if (!current) setError(message)
        return current
      })
    } finally {
      setLoading(false)
      setDashBusy(false)
    }
  }, [token])

  const refreshLeaderboardState = useCallback(async () => {
    if (!token || !metrics?.competition_id) return
    try {
      const res = await fetch(`${API_BASE}/leaderboard/${metrics.competition_id}`)
      if (!res.ok) return
      const data = (await res.json()) as { visible: boolean }
      setLeaderboardVisible(data.visible)
    } catch {
      // best effort
    }
  }, [token, metrics?.competition_id])

  const refreshLive = useCallback(async () => {
    if (!token) return
    try {
      const l = await api.adminLiveLogs(undefined, token)
      setLive(l)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load monitor.')
    }
  }, [token])

  const refreshAnalytics = useCallback(async () => {
    if (!token) return
    try {
      const response = await api.adminAnalytics(token)
      // Backend returns {analytics: {...}}, extract the inner object
      const a = response.analytics ?? response
      setAnalytics(a)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load analytics.')
    }
  }, [token])

  const refreshEval = useCallback(async () => {
    if (!token) return
    try {
      const payload = await api.adminEvalLogs(evalLogSeq.current, token)
      setEvalRun(payload.run)
      if (payload.logs.length) {
        setEvalLogs((prev) => {
          const seen = new Set(prev.map((l) => l.seq))
          const next = [...prev]
          for (const row of payload.logs) {
            if (!seen.has(row.seq)) next.push(row)
          }
          return next.slice(-300)
        })
        evalLogSeq.current = Math.max(
          evalLogSeq.current,
          ...payload.logs.map((l) => l.seq),
        )
      }
    } catch {
      // keep last snapshot
    }
  }, [token])

  useEffect(() => {
    if (!token) return
    setLoading(true)
    refreshDashboard()
    void refreshEval()
  }, [token, refreshDashboard, refreshEval])

  useEffect(() => {
    if (!token || !metrics) return
    refreshLeaderboardState()
  }, [token, metrics, refreshLeaderboardState])

  // Periodic live monitor poll (approx 3s).
  useEffect(() => {
    if (!token || phase !== 'monitor') return
    refreshLive()
    pollRef.current = window.setInterval(refreshLive, 3000)
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [token, phase, refreshLive])

  useEffect(() => {
    if (token && phase === 'cost') refreshAnalytics()
  }, [token, phase, refreshAnalytics])

  useEffect(() => {
    if (!token || evalRun?.status !== 'running') return
    const id = window.setInterval(() => {
      void refreshEval()
      void refreshDashboard()
    }, 1500)
    return () => window.clearInterval(id)
  }, [token, evalRun?.status, refreshEval, refreshDashboard])

  const handleLogin = async () => {
    if (!username.trim() || !password) {
      setLoginError('Enter username and password.')
      return
    }
    try {
      const res = await api.adminLogin(username.trim(), password)
      setAdminToken(res.token)
      setAdminTokenState(res.token)
      setLoginError('')
      setError('')
      setMetrics(null)
    } catch (e) {
      setLoginError(e instanceof Error ? e.message : 'Login failed.')
    }
  }

  const handleLogout = () => {
    clearAdminSession()
    setAdminTokenState(null)
    setMetrics(null)
    setLive(null)
    setAnalytics(null)
    setLeaderboardVisible(null)
  }

  const handleToggleLeaderboard = async () => {
    if (!token) return
    setLeaderboardBusy(true)
    try {
      if (leaderboardVisible) {
        await api.adminUnpublishLeaderboard(token)
        setLeaderboardVisible(false)
      } else {
        await api.adminPublishLeaderboard(token)
        setLeaderboardVisible(true)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to toggle leaderboard.')
    } finally {
      setLeaderboardBusy(false)
    }
  }

  const handleStartEval = async () => {
    if (!token) return
    setEvalBusy(true)
    try {
      const res = await api.adminStartEval(
        { batch_size: 8, concurrency: 4, max_retries: 3 },
        token,
      )
      setEvalRun(res)
      if (res.accepted === false) {
        setQueueNote('An evaluation run is already in progress.')
      } else {
        setEvalLogs([])
        evalLogSeq.current = 0
        setQueueNote('Evaluation started. Prompts stay stored until this run finishes.')
        await refreshEval()
        await refreshDashboard()
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start evaluation.')
    } finally {
      setEvalBusy(false)
    }
  }

  const handleToggleStatus = async () => {
    if (!token) return
    const current = metrics?.competition_status
    const opening = current !== 'OPEN'
    if (!opening && !window.confirm('Close submissions? New QR logins and submissions will be rejected.')) {
      return
    }
    setStatusBusy(true)
    try {
      if (opening) {
        await api.adminOpenCompetition(token)
        setQueueNote('Submissions reopened. New logins and submissions accepted.')
      } else {
        await api.adminCloseCompetition(token)
        setQueueNote('Submissions closed. New logins and submissions are rejected.')
      }
      await refreshDashboard()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not update competition status.')
    } finally {
      setStatusBusy(false)
    }
  }

  const handleCleanup = useCallback(async () => {
    if (!token) return
    if (!window.confirm('Delete ALL TEST competition data from Supabase? This runs the mandatory stress-test cleanup.')) {
      return
    }
    try {
      const res: CleanupResult = await api.adminTestCleanup(token)
      setExportNote(
        `Cleanup done: ${res.deleted_participants} participants, ${res.deleted_logs} request logs removed.`,
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Cleanup failed.')
    }
  }, [token])

  if (!token) {
    return (
      <AdminShell signedIn={false} onSignOut={handleLogout}>
        <section className="container flex min-h-[55vh] items-center justify-center py-16">
          <Card className="w-full max-w-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldCheck className="h-5 w-5" /> Admin sign in
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="admin-user">Username</Label>
                <Input
                  id="admin-user"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="admin-pass">Password</Label>
                <Input
                  id="admin-pass"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
                />
              </div>
              {loginError ? (
                <p className="text-sm text-destructive" role="alert">
                  {loginError}
                </p>
              ) : null}
              <Button className="w-full" onClick={handleLogin}>
                Sign in
              </Button>
            </CardContent>
          </Card>
        </section>
      </AdminShell>
    )
  }

  if (loading && !metrics) {
    return (
      <AdminShell signedIn onSignOut={handleLogout}>
        <div className="container py-16">
          <Spinner />
          <p className="mt-3 text-sm text-muted-foreground">Loading dashboard…</p>
        </div>
      </AdminShell>
    )
  }

  if (!metrics) {
    return (
      <AdminShell signedIn onSignOut={handleLogout}>
        <section className="container py-16">
          <div className="mx-auto max-w-md rounded-lg border border-destructive/30 bg-destructive/5 p-6 text-sm">
            <p className="font-medium text-destructive" role="alert">
              {error || 'Could not load the admin dashboard.'}
            </p>
            <Button className="mt-4" variant="outline" onClick={() => { setLoading(true); refreshDashboard() }}>
              Try again
            </Button>
          </div>
        </section>
      </AdminShell>
    )
  }

  const nav: { key: Tab; label: string }[] = [
    { key: 'dashboard', label: 'Dashboard' },
    { key: 'monitor', label: 'Live monitor' },
    { key: 'cost', label: 'Cost & analytics' },
    { key: 'criteria', label: 'Criteria' },
    { key: 'stress', label: 'Stress test' },
    { key: 'export', label: 'Export' },
  ]

  return (
    <AdminShell signedIn onSignOut={handleLogout}>
      <section className="relative container py-8 md:py-12">
        {/* Background decoration */}
        <div className="absolute inset-0 -z-10 dot-grid opacity-20" />
        <div>
          <p className="text-sm font-medium tracking-wide uppercase text-muted-foreground">
            Admin · Operations
          </p>
          <h1 className="mt-1 text-4xl font-semibold tracking-tight font-display">
            Control Room
          </h1>
        </div>

        <nav className="mt-6 flex flex-wrap gap-1 border-b border-border">
          {nav.map((n) => (
            <button
              key={n.key}
              type="button"
              role="tab"
              aria-selected={phase === n.key}
              onClick={() => setPhase(n.key)}
              className={`rounded-t-md px-4 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                phase === n.key
                  ? 'border-b-2 border-foreground text-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {n.label}
            </button>
          ))}
        </nav>

        {error ? (
          <div className="mt-4 flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
            <button className="ml-auto" onClick={() => setError('')} aria-label="Dismiss">
              <X className="h-4 w-4" />
            </button>
          </div>
        ) : null}

        {phase === 'dashboard' && (
          <div className="mt-8">
            <div className="flex flex-wrap items-center justify-end gap-3">
              <Button
                size="sm"
                variant="outline"
                onClick={() => refreshDashboard()}
                disabled={dashBusy}
              >
                {dashBusy ? <Spinner className="h-4 w-4" /> : <RefreshCw className="h-4 w-4" />} Refresh
              </Button>
              <Button
                size="sm"
                variant={metrics.competition_status === 'OPEN' ? 'outline' : 'default'}
                onClick={handleToggleStatus}
                disabled={statusBusy}
              >
                {metrics.competition_status === 'OPEN' ? (
                  <><Lock className="h-4 w-4" /> Stop accepting responses</>
                ) : (
                  <><LockOpen className="h-4 w-4" /> Open submissions</>
                )}
              </Button>
              <Button
                size="sm"
                onClick={handleStartEval}
                disabled={evalBusy || evalRun?.status === 'running'}
              >
                {evalBusy || evalRun?.status === 'running' ? (
                  <Spinner className="h-4 w-4" />
                ) : (
                  <Play className="h-4 w-4" />
                )}
                {evalRun?.status === 'running' ? 'Evaluating…' : 'Start Eval'}
              </Button>
              <Button size="sm" onClick={() => setPhase('stress')}>
                <Gauge className="h-4 w-4" /> Stress test
              </Button>
              <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm">
                {leaderboardVisible ? (
                  <>
                    <Eye className="h-4 w-4 text-emerald-600" />
                    <span>Leaderboard <strong className="text-emerald-700">published</strong></span>
                  </>
                ) : (
                  <>
                    <EyeOff className="h-4 w-4 text-muted-foreground" />
                    <span>Leaderboard <strong>hidden</strong></span>
                  </>
                )}
                <Button
                  size="sm"
                  variant={leaderboardVisible ? 'outline' : 'default'}
                  onClick={handleToggleLeaderboard}
                  disabled={leaderboardBusy}
                >
                  {leaderboardVisible ? 'Unpublish' : 'Publish leaderboard'}
                </Button>
              </div>
            </div>
            {queueNote ? (
              <p className="mt-2 text-xs text-muted-foreground text-right" role="status">
                {queueNote}
              </p>
            ) : (
              <p className="mt-2 text-xs text-muted-foreground text-right">
                Submissions are stored only. Start Eval queues and scores them in batches.
              </p>
            )}
            <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Stat label="Total participants" value={metrics.total_participants} />
              <Stat label="Submitted" value={metrics.submitted} />
              <Stat label="Prompts stored" value={metrics.total_prompts} />
              <Stat label="Awaiting eval" value={metrics.awaiting_eval ?? Math.max(0, metrics.total_prompts - metrics.evaluated)} />
              <Stat label="Evaluated" value={metrics.evaluated} />
              <Stat label="Queued jobs" value={metrics.queued} />
              <Stat label="Retrying / processing" value={metrics.retrying} />
              <Stat label="Failed evaluations" value={metrics.evaluation_failed} />
              <Stat label="Completed submissions" value={metrics.completed} />
              <Stat label="Average score" value={metrics.avg_score} />
              <Stat label="Median score" value={metrics.median_score} />
              <Stat label="Highest score" value={metrics.highest_score} />
            </div>
            {metrics.per_category && Object.keys(metrics.per_category).length > 0 ? (
              <div className="mt-6">
                <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
                  Per-category intake
                </h2>
                <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {Object.values(metrics.per_category)
                    .sort((a, b) => a.question_number - b.question_number)
                    .map((c) => {
                      const pct = c.stored > 0 ? Math.min(100, Math.round((c.evaluated / c.stored) * 100)) : 0
                      return (
                        <div key={c.question_number} className="rounded-lg border border-border p-4">
                          <div className="flex items-center justify-between">
                            <div className="text-sm font-medium">
                              {c.question_number}. {c.title}
                            </div>
                          </div>
                          <div className="mt-3 flex items-baseline justify-between text-sm">
                            <span className="text-muted-foreground">
                              <strong className="text-foreground tabular-nums">{c.stored}</strong> submitted
                            </span>
                            <span className="text-muted-foreground">
                              <strong className="text-foreground tabular-nums">{c.evaluated}</strong> evaluated
                            </span>
                          </div>
                          <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-muted">
                            <div
                              className="h-full bg-emerald-600 transition-all duration-300"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <div className="mt-1 text-right text-xs text-muted-foreground tabular-nums">
                            {pct}%
                          </div>
                        </div>
                      )
                    })}
                </div>
              </div>
            ) : null}
            {evalRun ? (
              <Card className="mt-6">
                <CardHeader>
                  <CardTitle className="text-base">Evaluation run</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm text-muted-foreground">
                    Status <span className="font-medium text-foreground">{evalRun.status}</span>
                    {' · '}enqueued {evalRun.enqueued}
                    {' · '}processed {evalRun.processed}
                    {' · '}completed {evalRun.completed}
                    {' · '}failed {evalRun.failed}
                  </p>
                  <div className="max-h-56 overflow-auto rounded-md border border-border bg-muted/30 p-3 font-mono text-xs leading-relaxed">
                    {evalLogs.length === 0 ? (
                      <p className="text-muted-foreground">No eval logs yet. Start Eval to stream progress.</p>
                    ) : (
                      evalLogs.map((row) => (
                        <div key={row.seq}>
                          [{row.level}] {row.message}
                        </div>
                      ))
                    )}
                  </div>
                </CardContent>
              </Card>
            ) : null}
          </div>
        )}

        {phase === 'monitor' && (
          <div className="mt-8 space-y-6">
            {live ? (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <Stat label="Requests / sec (window)" value={live.stats.rps} />
                <Stat label="Requests last 60s" value={live.stats.requests_last_60s} />
                <Stat label="Avg latency (ms)" value={live.stats.avg_latency_ms} />
                <Stat label="5xx errors (60s)" value={live.stats.error_count_60s} />
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Loading live metrics…</p>
            )}

            <LiveLogTable live={live} />
          </div>
        )}

        {phase === 'cost' && <CostPanel analytics={analytics} />}

        {phase === 'criteria' && (
          <CriteriaPanel token={token} onError={setError} onNote={setExportNote} />
        )}

        {phase === 'stress' && (
          <StressPanel
            token={token}
            onError={setError}
            onNote={setExportNote}
            onCleanup={handleCleanup}
          />
        )}

        {phase === 'export' && (
          <ExportPanel onError={setError} onNote={setExportNote} onCleanup={handleCleanup} />
        )}

        {exportNote ? (
          <div className="mt-6 flex items-start gap-2 rounded-lg border border-border bg-muted/40 p-3 text-sm">
            <Activity className="mt-0.5 h-4 w-4" />
            <span>{exportNote}</span>
            <button className="ml-auto" onClick={() => setExportNote('')} aria-label="Dismiss">
              <X className="h-4 w-4" />
            </button>
          </div>
        ) : null}
      </section>
    </AdminShell>
  )
}

function LiveLogTable({ live }: { live: LiveLogsResponse | null }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Live request log</CardTitle>
      </CardHeader>
      <CardContent>
        {!live || live.logs.length === 0 ? (
          <p className="text-sm text-muted-foreground">No requests logged yet.</p>
        ) : (
          <div className="max-h-96 overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-background">
                <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
                  <th className="px-2 py-2">When</th>
                  <th className="px-2 py-2">Method</th>
                  <th className="px-2 py-2">Path</th>
                  <th className="px-2 py-2">Status</th>
                  <th className="px-2 py-2">Latency</th>
                </tr>
              </thead>
              <tbody>
                {live.logs.map((l) => (
                  <tr key={l.id} className="border-b border-border/60">
                    <td className="px-2 py-1.5 tabular-nums text-muted-foreground">
                      {new Date(l.created_at).toLocaleTimeString()}
                    </td>
                    <td className="px-2 py-1.5">{l.method}</td>
                    <td className="px-2 py-1.5 break-all">{l.path}</td>
                    <td className="px-2 py-1.5 tabular-nums">{l.status}</td>
                    <td className="px-2 py-1.5 tabular-nums">{l.latency_ms}ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function CostPanel({ analytics }: { analytics: Analytics | null }) {
  if (!analytics) return <p className="py-8 text-sm text-muted-foreground">Loading analytics…</p>
  const cost = analytics.cost
  // Defensive checks for missing data
  if (!cost) {
    return <p className="py-8 text-sm text-muted-foreground">No cost data available yet.</p>
  }
  return (
    <div className="mt-8 space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Total evaluations" value={cost.total_evaluations ?? 0} />
        <Stat label="Input tokens" value={cost.total_input_tokens ?? 0} />
        <Stat label="Output tokens" value={cost.total_output_tokens ?? 0} />
        <Stat label="Estimated cost (USD)" value={cost.estimated_cost_usd ?? 0} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Per-category averages</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Object.values(analytics.per_category ?? {})
              .sort((a, b) => a.question_number - b.question_number)
              .map((c, idx) => {
                const stored = c.stored ?? 0
                const evaluated = c.evaluated ?? 0
                const pct = stored > 0 ? Math.min(100, Math.round((evaluated / stored) * 100)) : 0
                return (
                  <div key={c.question_number ?? idx} className="rounded-lg border border-border p-4">
                    <div className="text-sm font-medium">
                      {c.question_number ?? '—'}. {c.title ?? 'Untitled'}
                    </div>
                    <div className="mt-3 flex items-baseline gap-2">
                      <span className="text-2xl font-semibold tabular-nums">
                        {c.avg_score ?? '—'}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        avg of {evaluated} evaluated
                      </span>
                    </div>
                    <div className="mt-3 space-y-1.5">
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span>{stored} submitted</span>
                        <span>{evaluated} evaluated</span>
                      </div>
                      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full bg-emerald-600 transition-all duration-300"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <div className="text-right text-xs text-muted-foreground tabular-nums">
                        {pct}% evaluated
                      </div>
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      min {c.min_score ?? '—'} · max {c.max_score ?? '—'}
                    </div>
                  </div>
                )
              })}
            {Object.keys(analytics.per_category ?? {}).length === 0 ? (
              <p className="col-span-full text-sm text-muted-foreground">No per-category data yet.</p>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Cost by model</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-muted-foreground">
                <tr className="border-b border-border">
                  <th className="px-2 py-2">Model</th>
                  <th className="px-2 py-2">Evals</th>
                  <th className="px-2 py-2">In</th>
                  <th className="px-2 py-2">Out</th>
                  <th className="px-2 py-2">Think</th>
                  <th className="px-2 py-2">Cost USD</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(cost.per_model ?? {}).map(([model, m]) => (
                  <tr key={model} className="border-b border-border/60">
                    <td className="px-2 py-1.5">{model}</td>
                    <td className="px-2 py-1.5 tabular-nums">{m.evaluations ?? 0}</td>
                    <td className="px-2 py-1.5 tabular-nums">{m.input_tokens ?? 0}</td>
                    <td className="px-2 py-1.5 tabular-nums">{m.output_tokens ?? 0}</td>
                    <td className="px-2 py-1.5 tabular-nums">{m.thinking_tokens ?? 0}</td>
                    <td className="px-2 py-1.5 tabular-nums">{m.cost_usd ?? 0}</td>
                  </tr>
                ))}
                {Object.keys(cost.per_model ?? {}).length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-2 py-3 text-muted-foreground">
                      No evaluations recorded yet.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function StressPanel({
  token,
  onError,
  onNote,
  onCleanup,
}: {
  token: string
  onError: (m: string) => void
  onNote: (m: string) => void
  onCleanup: () => void
}) {
  const [total, setTotal] = useState(300)
  const [status, setStatus] = useState<StressStatus | null>(null)
  const [starting, setStarting] = useState(false)
  const pollRef = useRef<number | null>(null)

  const loadStatus = useCallback(async () => {
    try {
      const s = await api.adminStressStatus(token)
      setStatus(s)
      return s
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Could not load stress-test status.')
      return null
    }
  }, [token, onError])

  useEffect(() => {
    loadStatus()
  }, [loadStatus])

  useEffect(() => {
    if (status?.status !== 'running') {
      if (pollRef.current) window.clearInterval(pollRef.current)
      pollRef.current = null
      return
    }
    pollRef.current = window.setInterval(() => {
      void loadStatus()
    }, 1500)
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [status?.status, loadStatus])

  const handleStart = async () => {
    setStarting(true)
    try {
      const s = await api.adminStartStress({ total }, token)
      setStatus(s)
      if (s.accepted === false) {
        onError('A stress test is already running. Wait for it to finish.')
      } else {
        onNote(`Stress test started: ${s.total} sequential submissions.`)
      }
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Could not start the stress test.')
    } finally {
      setStarting(false)
    }
  }

  const running = status?.status === 'running'
  const pct =
    status && status.total > 0 ? Math.min(100, Math.round((status.completed / status.total) * 100)) : 0

  const statusCodes = status?.status_codes ?? {}

  return (
    <div className="mt-8 space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Gauge className="h-4 w-4" /> Isolated TEST competition load
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Seeds store-only TEST submissions sequentially, un-throttled, then runs Start Eval
            against that isolated competition. This is the realistic load a single Render free
            instance sustains when many students submit at once (e.g. 300 students ≈ 300 requests).
            Live participants are not touched. Clean up TEST rows when you are done.
          </p>
          <div className="max-w-xs space-y-1.5">
            <Label htmlFor="stress-total">Total submissions (max 1250)</Label>
            <Input
              id="stress-total"
              type="number"
              min={1}
              max={1250}
              value={total}
              disabled={running || starting}
              onChange={(e) => setTotal(Number(e.target.value))}
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={handleStart} disabled={running || starting}>
              {starting || running ? <Spinner className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              {running ? 'Running…' : 'Run stress test'}
            </Button>
            <Button variant="destructive" size="default" onClick={onCleanup} disabled={running}>
              <Trash2 className="h-4 w-4" /> Clean up TEST data
            </Button>
          </div>
          {status ? (
            <div className="space-y-3 rounded-lg border border-border p-4" aria-live="polite">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium capitalize">{status.phase ? `${status.status} · ${status.phase}` : status.status}</span>
                <span className="tabular-nums text-muted-foreground">
                  {status.completed} / {status.total || '—'}
                </span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                <div className="h-full bg-foreground transition-all duration-300" style={{ width: `${pct}%` }} />
              </div>
              <div className="grid gap-3 sm:grid-cols-4">
                <Stat label="Succeeded" value={status.succeeded} />
                <Stat label="Errors" value={status.errors} />
                <Stat label="Eval jobs done" value={status.jobs_completed ?? 0} />
                <Stat label="Eval jobs failed" value={status.jobs_failed ?? 0} />
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <Stat label="Avg latency (ms)" value={status.avg_latency_ms} />
                <Stat label="Max latency (ms)" value={status.max_latency_ms} />
                <Stat label="p95 latency (ms)" value={status.p95_latency_ms} />
              </div>
              {Object.keys(statusCodes).length > 0 ? (
                <div className="text-xs text-muted-foreground">
                  Status codes:{' '}
                  {Object.entries(statusCodes)
                    .sort((a, b) => Number(a[0]) - Number(b[0]))
                    .map(([code, n]) => `${code}: ${n}`)
                    .join('  ·  ')}
                </div>
              ) : null}
              {status.error_message ? (
                <p className="text-sm text-destructive">{status.error_message}</p>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No run yet. Start a test to see live progress here.</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function CriteriaPanel({
  token,
  onError,
  onNote,
}: {
  token: string
  onError: (m: string) => void
  onNote: (m: string) => void
}) {
  const categories = [
    { n: 1, label: 'Meme Generation' },
    { n: 2, label: 'AI Visual Art Creation' },
    { n: 3, label: 'AI Digital Storytelling / Creative Writing' },
    { n: 4, label: 'AI Song Factory' },
    { n: 5, label: 'AI-Generated Poetry in Local Languages' },
  ]
  const [entries, setEntries] = useState<CriteriaEntry[]>([])
  const [preview, setPreview] = useState<{ category: number; md: string } | null>(null)
  const [busyCategory, setBusyCategory] = useState<number | null>(null)

  const load = useCallback(async () => {
    try {
      setEntries(await api.adminCriteriaList(token))
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Could not load criteria.')
    }
  }, [token, onError])

  useEffect(() => {
    load()
  }, [load])

  const getEntry = (n: number) => entries.find((e) => e.question_number === n)

  const handleUpload = async (n: number, file: File) => {
    setBusyCategory(n)
    try {
      await api.adminCriteriaUpload(n, file, token)
      onNote(`Criteria uploaded for category ${n}. It will be used the next time evaluation runs.`)
      await load()
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Could not upload criteria.')
    } finally {
      setBusyCategory(null)
    }
  }

  const handlePreview = async (n: number) => {
    try {
      const d = await api.adminCriteriaDetail(n, token)
      setPreview({ category: n, md: d.content_md })
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Could not load criteria.')
    }
  }

  return (
    <div className="mt-8 space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileText className="h-4 w-4" /> Evaluation criteria (markdown per category)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Upload one markdown rubric per category. The rubric is injected into the evaluator so
            prompts in that category are scored against these instructions. Criteria apply from the
            next evaluation run onward.
          </p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {categories.map((c) => {
              const entry = getEntry(c.n)
              return (
                <div key={c.n} className="rounded-lg border border-border p-4">
                  <div className="text-sm font-medium">
                    {c.n}. {c.label}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {entry ? (
                      <>
                        {entry.file_name}
                        {entry.updated_at
                          ? ` · ${new Date(entry.updated_at).toLocaleDateString()}`
                          : ''}
                      </>
                    ) : (
                      'No criteria uploaded yet'
                    )}
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:border-foreground/40">
                      {busyCategory === c.n ? <Spinner className="h-3.5 w-3.5" /> : <Upload className="h-3.5 w-3.5" />}
                      {busyCategory === c.n ? 'Uploading…' : 'Upload .md'}
                      <input
                        type="file"
                        accept=".md,.markdown,text/markdown"
                        className="sr-only"
                        disabled={busyCategory !== null}
                        onChange={(e) => {
                          const f = e.target.files?.[0]
                          if (f) void handleUpload(c.n, f)
                          e.target.value = ''
                        }}
                      />
                    </label>
                    {entry ? (
                      <Button size="sm" variant="outline" onClick={() => handlePreview(c.n)}>
                        <Eye className="h-3.5 w-3.5" /> Preview
                      </Button>
                    ) : null}
                  </div>
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>

      {preview ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between text-base">
              <span>Category {preview.category} — criteria preview</span>
              <Button size="sm" variant="outline" onClick={() => setPreview(null)}>
                <X className="h-4 w-4" /> Close
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-md border border-border bg-muted/40 p-4 font-mono text-xs leading-relaxed">
              {preview.md || 'No content.'}
            </pre>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}

function ExportPanel({
  onError,
  onNote,
  onCleanup,
}: {
  onError: (m: string) => void
  onNote: (m: string) => void
  onCleanup: () => void
}) {
  const categories = [
    { n: 1, label: 'Meme Generation' },
    { n: 2, label: 'AI Visual Art Creation' },
    { n: 3, label: 'AI Digital Storytelling / Creative Writing' },
    { n: 4, label: 'AI Song Factory' },
    { n: 5, label: 'AI-Generated Poetry in Local Languages' },
  ]
  const open = (url: string) => {
    const token = getAdminToken()
    const full = `${API_BASE}${url}`
    fetch(full, { headers: { Authorization: `Bearer ${token ?? ''}` } })
      .then((res) => {
        if (!res.ok) throw new Error('Export failed')
        return res.blob()
      })
      .then((blob) => {
        const link = window.document.createElement('a')
        const objectUrl = window.URL.createObjectURL(blob)
        link.href = objectUrl
        link.download = url.includes('.csv') ? 'prompts.csv' : 'prompts'
        link.click()
        window.URL.revokeObjectURL(objectUrl)
        onNote('Download started.')
      })
      .catch((e) => onError(e instanceof Error ? e.message : 'Export failed.'))
  }
  return (
    <div className="mt-8 space-y-4">
      <div className="rounded-lg border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
        Export produces category-wise, sequential output (Category 1 rows, then Category 2, …),
        each block ordered by score. Use the per-category buttons to export one category as its own CSV.
      </div>
      <Button onClick={() => open(api.adminExportUrl())}>
        <Download className="mr-1 h-4 w-4" /> Export all categories (CSV, category-wise)
      </Button>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {categories.map((c) => (
          <button
            key={c.n}
            type="button"
            onClick={() => open(api.adminExportUrl(c.n))}
            className="flex items-center justify-between rounded-lg border border-border p-4 text-left hover:border-foreground/40"
          >
            <span>
              <span className="block text-sm font-medium">{c.n}. {c.label}</span>
            </span>
            <Download className="h-4 w-4 text-muted-foreground" />
          </button>
        ))}
      </div>

      <div className="mt-6 rounded-lg border border-destructive/30 bg-destructive/5 p-4">
        <div className="flex items-start gap-2">
          <Trash2 className="mt-0.5 h-4 w-4 text-destructive" />
          <div>
            <div className="font-medium text-destructive">Stress-test cleanup</div>
            <p className="mt-1 text-sm text-muted-foreground">
              Deletes every row belonging to the isolated TEST competition (
              participants, submissions, responses, evaluations, jobs, request
              logs). Run after a load test to leave Supabase pristine.
            </p>
            <Button variant="destructive" size="sm" className="mt-3" onClick={onCleanup}>
              Clean up TEST data
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}