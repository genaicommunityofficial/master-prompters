import type { ReactNode } from 'react'
import type { EvalProgress } from '@/types'
import { Stat } from './Stat'

function usd(value: number | null | undefined): string {
  return `$${Number(value ?? 0).toFixed(4)}`
}

export function EvalProgressPanel({
  status,
  title,
  className,
  compact = false,
  children,
}: {
  status: EvalProgress | null
  title: string
  className?: string
  compact?: boolean
  children?: ReactNode
}) {
  if (!status) {
    return (
      <div className={className}>
        <p className="text-sm text-muted-foreground">Loading evaluation status…</p>
      </div>
    )
  }
  const { totals, jobs, per_category, top_errors, failed_sample, cost, run } = status
  const progressPct = totals.progress_pct ?? 0
  const running = run?.status === 'running'
  const jobFailed = totals.job_failed ?? jobs.FAILED ?? 0

  return (
    <div className={className}>
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium uppercase tracking-wide text-muted-foreground">{title}</h2>
        {running ? <span className="text-xs tabular-nums text-muted-foreground">live</span> : null}
      </div>

      <div className="mt-4 rounded-lg border border-border p-4">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Overall progress</span>
          <span className="tabular-nums">{progressPct.toFixed(1)}%</span>
        </div>
        <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full bg-foreground transition-all duration-300"
            style={{ width: `${Math.min(100, progressPct)}%` }}
          />
        </div>
        {running ? (
          <p className="mt-2 text-xs tabular-nums text-muted-foreground">
            {run?.rate_per_second ? `${run.rate_per_second.toFixed(2)} evals/s` : '…'}
            {run?.eta_seconds ? ` · ~${Math.round(run.eta_seconds)}s remaining` : ''}
          </p>
        ) : null}
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Submitted" value={totals.submitted} />
        <Stat label="Evaluated" value={totals.evaluated} />
        <Stat label="Pending" value={totals.pending} />
        <Stat label="Est. cost" value={usd(cost.estimated_cost_usd)} />
      </div>

      {!compact ? (
        <>
          <details className="mt-6">
            <summary className="cursor-pointer text-sm font-medium text-muted-foreground">
              Job queue · failed {jobFailed}
            </summary>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {(['QUEUED', 'PROCESSING', 'RETRY', 'COMPLETED', 'FAILED'] as const).map((key) => (
                <Stat key={key} label={key.toLowerCase()} value={jobs[key]} />
              ))}
            </div>
          </details>

          {Object.keys(per_category).length > 0 ? (
            <div className="mt-6">
              <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Per category
              </h3>
              <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {Object.values(per_category)
                  .sort((a, b) => a.question_number - b.question_number)
                  .map((c) => {
                    const pct = c.progress_pct ?? 0
                    return (
                      <div key={c.question_number} className="rounded-lg border border-border p-5">
                        <div className="text-sm font-medium">
                          {c.question_number}. {c.title}
                        </div>
                        <div className="mt-3 flex items-baseline justify-between text-sm">
                          <span className="text-muted-foreground">
                            <strong className="tabular-nums text-foreground">{c.stored}</strong> stored
                          </span>
                          <span className="text-muted-foreground">
                            <strong className="tabular-nums text-foreground">{c.evaluated}</strong> evaluated
                          </span>
                        </div>
                        <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                          <div className="h-full bg-foreground" style={{ width: `${Math.min(100, pct)}%` }} />
                        </div>
                        <div className="mt-2 text-right text-xs tabular-nums text-muted-foreground">
                          {pct.toFixed(0)}% · avg {c.avg_score ?? '—'}
                        </div>
                      </div>
                    )
                  })}
              </div>
            </div>
          ) : null}

          {top_errors.length > 0 ? (
            <div className="mt-6 rounded-lg border border-amber-500/30 bg-amber-500/5 p-4">
              <h3 className="text-xs font-medium uppercase tracking-wide">Top errors</h3>
              <ul className="mt-2 space-y-1 text-sm">
                {top_errors.map((e, i) => (
                  <li key={i} className="flex items-baseline gap-2">
                    <span className="tabular-nums">{e.count}×</span>
                    <span className="break-all">{e.message}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {failed_sample.length > 0 ? (
            <div className="mt-4 rounded-lg border border-destructive/30 bg-destructive/5 p-4">
              <h3 className="text-xs font-medium uppercase tracking-wide text-destructive">
                Failed jobs (sample)
              </h3>
              <ul className="mt-2 max-h-48 space-y-2 overflow-auto text-xs">
                {failed_sample.map((f, i) => (
                  <li key={i} className="text-muted-foreground">
                    <span className="tabular-nums">Q{f.question_number ?? '?'}</span>
                    {' · '}attempts {f.attempt_count ?? 0}
                    <span className="block break-all text-destructive/80">{f.error}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="mt-4 rounded-lg border border-border p-4 text-sm text-muted-foreground">
            Run <strong className="text-foreground">{run?.status ?? 'idle'}</strong>
            <span className="ml-3 tabular-nums">cost {usd(cost.estimated_cost_usd)}</span>
          </div>
        </>
      ) : null}

      {children}
    </div>
  )
}
