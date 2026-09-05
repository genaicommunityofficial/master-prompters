export type SiteLink = { label: string; to: string }

/** Public and participant chrome. Admin is never listed here. */
export function participantNavLinks(): SiteLink[] {
  return [
    { label: 'Enter', to: '/competition' },
    { label: 'Results', to: '/leaderboard' },
  ]
}

export function adminNavLinks(): SiteLink[] {
  return [
    { label: 'Dashboard', to: '/admin' },
    { label: 'Participants', to: '/admin/participants' },
    { label: 'Evaluation', to: '/admin/eval' },
    { label: 'Criteria', to: '/admin/criteria' },
    { label: 'Export', to: '/admin/export' },
  ]
}
