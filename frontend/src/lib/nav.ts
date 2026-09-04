export type SiteLink = { label: string; to: string }

/** Public and participant chrome. Admin is never listed here. */
export function participantNavLinks(): SiteLink[] {
  return [
    { label: 'Competition', to: '/competition' },
    { label: 'Leaderboard', to: '/leaderboard' },
  ]
}

export function adminNavLinks(): SiteLink[] {
  return [{ label: 'Control Room', to: '/admin' }]
}
