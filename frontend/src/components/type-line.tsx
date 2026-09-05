import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  )
}

const typed = new Set<string>()

/** Types one line. Caret stays on that line, then fades in place. */
export function TypeHeadline({
  text,
  className,
  ms = 42,
}: {
  text: string
  className?: string
  ms?: number
}) {
  const [shown, setShown] = useState(() => (typed.has(text) ? text : ''))
  const [caret, setCaret] = useState(() => !typed.has(text))

  useEffect(() => {
    if (prefersReducedMotion() || typed.has(text)) {
      setShown(text)
      setCaret(false)
      typed.add(text)
      return
    }

    let cancelled = false
    let i = 0
    let timer = 0

    const tick = () => {
      if (cancelled) return
      i += 1
      setShown(text.slice(0, i))
      if (i >= text.length) {
        typed.add(text)
        timer = window.setTimeout(() => {
          if (!cancelled) setCaret(false)
        }, 700)
        return
      }
      timer = window.setTimeout(tick, text[i - 1] === ' ' ? ms * 1.4 : ms)
    }

    timer = window.setTimeout(tick, 160)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [text, ms])

  return (
    <h1 className={cn('whitespace-nowrap', className)}>
      <span className="sr-only">{text}</span>
      <span aria-hidden="true">
        {shown}
        <span
          aria-hidden="true"
          className={cn(
            'ml-[0.12em] inline-block h-[0.78em] w-px translate-y-[0.06em] bg-current align-baseline',
            caret ? 'animate-caret' : 'opacity-0',
          )}
        />
      </span>
    </h1>
  )
}
