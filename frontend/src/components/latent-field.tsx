import { useEffect, useMemo, useState } from 'react'
import { cn } from '@/lib/utils'

const GLYPHS = ['·', '+', '*', '░', '▒', '#'] as const

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  )
}

function lcg(seed: number) {
  let state = seed >>> 0
  return () => {
    state = (Math.imul(1664525, state) + 1013904223) >>> 0
    return state / 0xffffffff
  }
}

function seedCells(count: number, seed: number) {
  const rand = lcg(seed)
  return Array.from({ length: count }, () => Math.floor(rand() * GLYPHS.length))
}

export function LatentField({
  rows,
  cols,
  className,
}: {
  rows: number
  cols: number
  className?: string
}) {
  const count = rows * cols
  const initial = useMemo(() => seedCells(count, 2026 * rows + cols), [count, rows, cols])
  const [cells, setCells] = useState(initial)

  useEffect(() => {
    setCells(seedCells(count, 2026 * rows + cols))
    if (prefersReducedMotion()) return undefined

    const rand = lcg(20260 + rows * 17 + cols)
    const id = window.setInterval(() => {
      setCells((prev) => {
        const next = prev.slice()
        for (let i = 0; i < 3; i += 1) {
          const idx = Math.floor(rand() * next.length)
          next[idx] = Math.floor(rand() * GLYPHS.length)
        }
        return next
      })
    }, 640)
    return () => window.clearInterval(id)
  }, [count, rows, cols])

  return (
    <div
      aria-hidden="true"
      className={cn(
        'grid pointer-events-none select-none font-pixel text-[10px] leading-none tracking-[0.22em]',
        className,
      )}
      style={{
        gridTemplateColumns: `repeat(${cols}, 0.7rem)`,
        gap: '0.32rem 0.28rem',
      }}
    >
      {cells.map((glyph, index) => (
        <span
          key={index}
          className={glyph >= 3 ? 'text-mark' : 'text-foreground/40'}
        >
          {GLYPHS[glyph]}
        </span>
      ))}
    </div>
  )
}
