export function Stat({
  label,
  value,
}: {
  label: string
  value: number | string | null | undefined
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="text-2xl font-semibold tabular-nums">{value ?? '-'}</div>
      <div className="mt-1 text-xs text-muted-foreground">{label}</div>
    </div>
  )
}
