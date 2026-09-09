import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useState, type ReactNode } from 'react'
import { Menu, X } from 'lucide-react'
import { ClubMark } from '@/components/club-mark'
import { Button } from '@/components/ui/button'
import { COMMUNITY_LINE, COMPETITION_NAME } from '@/lib/brand'
import { useSession } from '@/store/session'
import { adminNavLinks, participantNavLinks } from '@/lib/nav'
import { clearSession, getToken, api } from '@/services/api'
import { cn } from '@/lib/utils'

function SessionActions({
  signedIn,
  name,
  onSignOut,
}: {
  signedIn: boolean
  name?: string
  onSignOut: () => void
}) {
  if (signedIn) {
    return (
      <div className="flex flex-col items-stretch gap-2 md:flex-row md:items-center md:gap-3">
        {name ? (
          <p className="max-w-[14rem] truncate px-1 text-sm text-muted-foreground md:px-0" title={name}>
            {name}
          </p>
        ) : null}
        <Button type="button" size="sm" onClick={onSignOut}>
          Sign out
        </Button>
      </div>
    )
  }

  return (
    <Button asChild size="sm">
      <Link to="/" state={{ loginRequired: true }}>
        Sign in
      </Link>
    </Button>
  )
}

function BrandLockup({ to }: { to: string }) {
  return (
    <Link to={to} className="flex min-w-0 items-center gap-2.5">
      <ClubMark size={32} className="h-8 w-8" decorative />
      <span className="min-w-0">
        <span className="block truncate text-[13px] font-medium leading-tight">
          {COMPETITION_NAME}
        </span>
        <span className="mt-0.5 hidden truncate text-[11px] text-muted-foreground sm:block">
          {COMMUNITY_LINE}
        </span>
      </span>
    </Link>
  )
}

function HeaderFrame({
  className,
  brandTo,
  links,
  trailing,
}: {
  className?: string
  brandTo: string
  links: { label: string; to: string }[]
  trailing: ReactNode
}) {
  const [open, setOpen] = useState(false)
  return (
    <header
      className={cn(
        'sticky top-0 z-40 border-b border-mark/30 bg-background/88 backdrop-blur',
        className,
      )}
    >
      <div className="container flex min-h-16 items-center justify-between gap-4 py-2">
        <BrandLockup to={brandTo} />

        <nav className="hidden items-center justify-end gap-1 md:flex" aria-label="Primary">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.to === brandTo}
              className={({ isActive }) =>
                cn(
                  'rounded-md px-3 py-1.5 text-sm font-medium',
                  isActive
                    ? 'bg-muted text-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )
              }
            >
              {l.label}
            </NavLink>
          ))}
          {trailing}
        </nav>

        <button
          className="tap-highlight-none flex h-10 w-10 items-center justify-center rounded-md md:hidden"
          onClick={() => setOpen((o) => !o)}
          aria-label="Toggle menu"
          aria-expanded={open}
        >
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {open ? (
        <nav className="border-t border-border/60 bg-background md:hidden" aria-label="Primary">
          <div className="container flex flex-col gap-1 py-3">
            {links.map((l) => (
              <Button key={l.to} asChild variant="ghost" size="sm" onClick={() => setOpen(false)}>
                <Link to={l.to}>{l.label}</Link>
              </Button>
            ))}
            <div onClick={() => setOpen(false)}>{trailing}</div>
          </div>
        </nav>
      ) : null}
    </header>
  )
}

export function SiteHeader({ className }: { className?: string }) {
  const nav = useNavigate()
  const token = useSession((s) => s.token) ?? getToken()
  const name = useSession((s) => s.displayName)

  const handleLogout = async () => {
    try {
      await api.logout()
    } catch {
      // Still clear the browser so this device is signed out.
    }
    clearSession()
    useSession.getState().clear()
    nav('/')
  }

  const trailing = (
    <SessionActions signedIn={Boolean(token)} name={name} onSignOut={() => void handleLogout()} />
  )

  return (
    <HeaderFrame
      className={className}
      brandTo="/"
      links={participantNavLinks()}
      trailing={trailing}
    />
  )
}

function TestModeSwitch({
  testMode,
  onChange,
}: {
  testMode: boolean
  onChange: (next: boolean) => void
}) {
  return (
    <div
      role="group"
      aria-label="Competition scope"
      className="inline-flex rounded-md border border-border bg-muted p-0.5"
    >
      <button
        type="button"
        aria-pressed={!testMode}
        onClick={() => onChange(false)}
        className={cn(
          'rounded-[5px] px-2.5 py-1 text-xs font-medium transition-colors',
          testMode
            ? 'text-muted-foreground hover:text-foreground'
            : 'bg-background text-foreground shadow-sm',
        )}
      >
        Live
      </button>
      <button
        type="button"
        aria-pressed={testMode}
        onClick={() => onChange(true)}
        className={cn(
          'rounded-[5px] px-2.5 py-1 text-xs font-medium transition-colors',
          testMode
            ? 'bg-background text-foreground shadow-sm'
            : 'text-muted-foreground hover:text-foreground',
        )}
      >
        Test
      </button>
    </div>
  )
}

export function AdminHeader({
  className,
  signedIn,
  onSignOut,
  testMode = false,
  onTestModeChange,
}: {
  className?: string
  signedIn: boolean
  onSignOut: () => void
  testMode?: boolean
  onTestModeChange?: (next: boolean) => void
}) {
  const [open, setOpen] = useState(false)
  const links = signedIn ? adminNavLinks() : []

  return (
    <header
      className={cn(
        'sticky top-0 z-40 border-b border-border/60 bg-background/90 backdrop-blur',
        className,
      )}
    >
      <div className="container flex min-h-14 items-center justify-between gap-4 py-2.5">
        <BrandLockup to="/admin" />
        <div className="hidden items-center gap-4 md:flex">
          {signedIn && onTestModeChange ? (
            <TestModeSwitch testMode={testMode} onChange={onTestModeChange} />
          ) : null}
          {signedIn ? (
            <Button type="button" size="sm" onClick={onSignOut}>
              Sign out
            </Button>
          ) : null}
        </div>
        <button
          className="tap-highlight-none flex h-10 w-10 items-center justify-center rounded-md md:hidden"
          onClick={() => setOpen((o) => !o)}
          aria-label="Toggle menu"
          aria-expanded={open}
        >
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {signedIn ? (
        <nav className="hidden border-t border-border/60 md:block" aria-label="Admin">
          <div className="container flex items-center gap-1 py-2">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.to === '/admin'}
                className={({ isActive }) =>
                  cn(
                    'rounded-md px-3 py-2 text-sm font-medium',
                    isActive
                      ? 'bg-muted text-foreground'
                      : 'text-muted-foreground hover:text-foreground',
                  )
                }
              >
                {l.label}
              </NavLink>
            ))}
          </div>
        </nav>
      ) : null}

      {open ? (
        <nav className="border-t border-border/60 bg-background md:hidden" aria-label="Admin">
          <div className="container flex flex-col gap-2 py-3">
            {signedIn && onTestModeChange ? (
              <div className="px-1 py-1">
                <TestModeSwitch testMode={testMode} onChange={onTestModeChange} />
              </div>
            ) : null}
            {links.map((l) => (
              <Button key={l.to} asChild variant="ghost" size="sm" onClick={() => setOpen(false)}>
                <Link to={l.to}>{l.label}</Link>
              </Button>
            ))}
            {signedIn ? (
              <Button type="button" size="sm" onClick={onSignOut}>
                Sign out
              </Button>
            ) : null}
          </div>
        </nav>
      ) : null}
    </header>
  )
}

function Shell({
  children,
  header,
}: {
  children: ReactNode
  header: ReactNode
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:ring-2 focus:ring-ring"
      >
        Skip to content
      </a>
      {header}
      <main id="main" className="min-w-0 flex-1">
        {children}
      </main>
      <footer className="border-t border-border/60 py-8">
        <div className="container flex flex-col gap-1 text-sm text-muted-foreground sm:flex-row sm:items-baseline sm:justify-between">
          <p>{COMPETITION_NAME}</p>
          <p>Organised by the {COMMUNITY_LINE}</p>
        </div>
      </footer>
    </div>
  )
}

export function PageShell({ children }: { children: ReactNode }) {
  return <Shell header={<SiteHeader />}>{children}</Shell>
}

export function AdminShell({
  children,
  signedIn,
  onSignOut,
  testMode = false,
  onTestModeChange,
}: {
  children: ReactNode
  signedIn: boolean
  onSignOut: () => void
  testMode?: boolean
  onTestModeChange?: (next: boolean) => void
}) {
  return (
    <Shell
      header={
        <AdminHeader
          signedIn={signedIn}
          onSignOut={onSignOut}
          testMode={testMode}
          onTestModeChange={onTestModeChange}
        />
      }
    >
      {children}
    </Shell>
  )
}
