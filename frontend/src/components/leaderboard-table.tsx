import { Card, CardContent } from '@/components/ui/card'
import type { LeaderboardEntry } from '@/types'
import { cn } from '@/lib/utils'

function rankRowClass(rank: number): string {
  if (rank === 1) return 'bg-amber-100/90 dark:bg-amber-500/20'
  if (rank === 2) return 'bg-zinc-200/80 dark:bg-zinc-500/25'
  if (rank === 3) return 'bg-orange-100/80 dark:bg-orange-500/20'
  if (rank >= 4 && rank <= 10) return 'bg-stone-100 dark:bg-stone-500/15'
  return ''
}

function rankMarkClass(rank: number): string {
  if (rank === 1) return 'text-amber-800 dark:text-amber-200'
  if (rank === 2) return 'text-zinc-700 dark:text-zinc-200'
  if (rank === 3) return 'text-orange-800 dark:text-orange-200'
  return ''
}

export function LeaderboardTable({
  entries,
  emptyLabel = 'No scored results yet.',
}: {
  entries: LeaderboardEntry[]
  emptyLabel?: string
}) {
  return (
    <Card>
      <CardContent className="p-0">
        <div className="overflow-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-5 py-3 font-medium">Rank</th>
                <th className="px-5 py-3 font-medium">Participant</th>
                <th className="px-5 py-3 font-medium">Reg. no.</th>
                {[1, 2, 3, 4, 5].map((q) => (
                  <th key={q} className="px-3 py-3 text-right font-medium">
                    Q{q}
                  </th>
                ))}
                <th className="px-5 py-3 text-right font-medium">Total</th>
                <th className="px-5 py-3 text-right font-medium">Avg</th>
              </tr>
            </thead>
            <tbody>
              {entries.slice(0, 50).map((e, i) => (
                <tr
                  key={`${e.rank}-${e.registration_number ?? e.display_name}-${i}`}
                  className={cn(
                    'border-b border-border/60 last:border-0',
                    rankRowClass(e.rank),
                  )}
                >
                  <td className={cn('px-5 py-3.5 font-semibold tabular-nums', rankMarkClass(e.rank))}>
                    {e.rank}
                  </td>
                  <td className="px-5 py-3.5">{e.display_name}</td>
                  <td className="px-5 py-3.5 tabular-nums text-muted-foreground">
                    {e.registration_number || '—'}
                  </td>
                  {[1, 2, 3, 4, 5].map((q) => (
                    <td
                      key={q}
                      className="px-3 py-3.5 text-right tabular-nums text-muted-foreground"
                    >
                      {e.category_scores?.[q] ?? '-'}
                    </td>
                  ))}
                  <td className="px-5 py-3.5 text-right font-semibold tabular-nums">
                    {e.total_score}
                  </td>
                  <td className="px-5 py-3.5 text-right tabular-nums">
                    {e.average_score ?? '-'}
                  </td>
                </tr>
              ))}
              {entries.length === 0 ? (
                <tr>
                  <td colSpan={10} className="px-5 py-8 text-center text-muted-foreground">
                    {emptyLabel}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}
