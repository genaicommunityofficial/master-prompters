import { cn } from '@/lib/utils'
import { COMMUNITY_LINE } from '@/lib/brand'

export function ClubMark({
  className,
  size = 32,
  decorative = false,
}: {
  className?: string
  size?: number
  decorative?: boolean
}) {
  return (
    <img
      src="/club-mark.png"
      alt={decorative ? '' : COMMUNITY_LINE}
      width={size}
      height={size}
      className={cn('shrink-0 rounded-md', className)}
    />
  )
}
