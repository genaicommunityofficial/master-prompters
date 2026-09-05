import { AlertTriangle, X } from 'lucide-react'

export function Banner({
  message,
  onDismiss,
  tone = 'error',
}: {
  message: string
  onDismiss: () => void
  tone?: 'error' | 'note'
}) {
  if (!message) return null
  const error = tone === 'error'
  return (
    <div
      className={
        error
          ? 'flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive'
          : 'flex items-start gap-2 rounded-lg border border-border bg-muted/40 p-3 text-sm'
      }
      role={error ? 'alert' : 'status'}
    >
      {error ? <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> : null}
      <span>{message}</span>
      <button className="ml-auto" onClick={onDismiss} aria-label="Dismiss">
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}
