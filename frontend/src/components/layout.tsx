import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useState, type ReactNode } from 'react'
import { Menu, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useSession } from '@/store/session'
import { adminNavLinks, participantNavLinks } from '@/lib/nav'
import { clearSession, getToken } from '@/services/api'
import { cn } from '@/lib/utils'

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
        'sticky top-0 z-40 border-b border-border/60 bg-background/80 backdrop-blur',
        className,
      )}
    >
      <div className="container flex h-16 items-center justify-between">
        <Link to={brandTo} className="flex items-center gap-2 text-sm font-semibold tracking-tight">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground text-xs font-bold">
            Mp
          </span>
          <span>Master Prompters 2.0</span>
        </Link>

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

  const handleLogout = () => {
    clearSession()
    useSession.getState().clear()
    nav('/')
  }

  const trailing = token ? (
    <Button variant="ghost" size="sm" onClick={handleLogout}>
      Sign out {name ? `· ${name}` : ''}
    </Button>
  ) : null

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
    <div className="flex items-center gap-2">
      <span className={cn('text-xs', testMode ? 'text-muted-foreground' : 'font-medium text-foreground')}>
        Live
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={testMode}
        aria-label="Test mode"
        onClick={() => onChange(!testMode)}
        className={cn(
          'relative h-6 w-11 rounded-full transition-colors',
          testMode ? 'bg-foreground' : 'bg-muted',
        )}
      >
        <span
          className={cn(
            'absolute top-0.5 h-5 w-5 rounded-full bg-background shadow-sm transition-transform',
            testMode ? 'translate-x-5' : 'translate-x-0.5',
          )}
        />
      </button>
      <span className={cn('text-xs', testMode ? 'font-medium text-foreground' : 'text-muted-foreground')}>
        Test
      </span>
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
        <Link to="/admin" className="flex items-center gap-2 text-sm font-semibold tracking-tight">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground text-xs font-bold">
            Mp
          </span>
          <span>Master Prompters 2.0</span>
        </Link>
        <div className="hidden items-center gap-4 md:flex">
          {signedIn && onTestModeChange ? (
            <TestModeSwitch testMode={testMode} onChange={onTestModeChange} />
          ) : null}
          {signedIn ? (
            <Button variant="ghost" size="sm" onClick={onSignOut}>
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
              <Button variant="ghost" size="sm" onClick={onSignOut}>
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
      <main id="main" className="flex-1">
        {children}
      </main>
      <footer className="border-t border-border/60 py-8">
        <div className="container text-sm text-muted-foreground">
          Master Prompters 2.0 · Prompt Writing Competition
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
