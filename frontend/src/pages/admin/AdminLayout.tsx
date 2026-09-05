import { useState } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import { ShieldCheck } from 'lucide-react'
import { AdminShell } from '@/components/layout'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { isAdminApiAvailable } from '@/lib/runtime'
import {
  api,
  clearAdminSession,
  getAdminToken,
  setAdminToken,
} from '@/services/api'
import { ADMIN_TEST_MODE_KEY, LIVE_COMPETITION_ID, TEST_COMPETITION_ID } from './constants'
import type { AdminOutletContext } from './context'

function readTestMode(): boolean {
  if (typeof window === 'undefined') return false
  return window.localStorage.getItem(ADMIN_TEST_MODE_KEY) === '1'
}

export function AdminLayout() {
  const navigate = useNavigate()
  const [token, setTokenState] = useState<string | null>(getAdminToken())
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loginError, setLoginError] = useState('')
  const [testMode, setTestModeState] = useState(readTestMode)

  const setTestMode = (next: boolean) => {
    setTestModeState(next)
    window.localStorage.setItem(ADMIN_TEST_MODE_KEY, next ? '1' : '0')
  }

  const handleLogin = async () => {
    if (!username.trim() || !password) {
      setLoginError('Enter username and password.')
      return
    }
    try {
      const res = await api.adminLogin(username.trim(), password)
      setAdminToken(res.token)
      setTokenState(res.token)
      setLoginError('')
    } catch (e) {
      setLoginError(e instanceof Error ? e.message : 'Login failed.')
    }
  }

  const handleLogout = () => {
    clearAdminSession()
    setTokenState(null)
    navigate('/admin')
  }

  const competitionId = testMode ? TEST_COMPETITION_ID : LIVE_COMPETITION_ID
  const outlet: AdminOutletContext | null = token
    ? { token, competitionId, testMode }
    : null

  if (!isAdminApiAvailable()) {
    return (
      <AdminShell signedIn={false} onSignOut={handleLogout}>
        <section className="container flex min-h-[55vh] items-center justify-center py-16">
          <Card className="w-full max-w-md">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldCheck className="h-5 w-5" /> Admin runs on your laptop
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-muted-foreground">
              <p>
                This Vercel site is for participants only. Open and close the competition,
                run Gemini evaluation, and publish the leaderboard from the local app:
              </p>
              <p className="font-mono text-foreground">http://localhost:5173/admin</p>
              <p>
                Start FastAPI on this machine first, then reload the leaderboard page here
                after you publish results.
              </p>
            </CardContent>
          </Card>
        </section>
      </AdminShell>
    )
  }

  if (!token) {
    return (
      <AdminShell signedIn={false} onSignOut={handleLogout}>
        <section className="container flex min-h-[55vh] items-center justify-center py-16">
          <Card className="w-full max-w-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldCheck className="h-5 w-5" /> Admin sign in
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="admin-user">Username</Label>
                <Input
                  id="admin-user"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="admin-pass">Password</Label>
                <Input
                  id="admin-pass"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && void handleLogin()}
                />
              </div>
              {loginError ? (
                <p className="text-sm text-destructive" role="alert">
                  {loginError}
                </p>
              ) : null}
              <Button className="w-full" onClick={() => void handleLogin()}>
                Sign in
              </Button>
            </CardContent>
          </Card>
        </section>
      </AdminShell>
    )
  }

  return (
    <AdminShell signedIn onSignOut={handleLogout} testMode={testMode} onTestModeChange={setTestMode}>
      <section className="relative container py-8 md:py-10">
        <div className="absolute inset-0 -z-10 dot-grid opacity-20" />
        {testMode ? (
          <p className="mb-6 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            Test mode · scoped to <span className="font-medium text-foreground">{TEST_COMPETITION_ID}</span>
            . Public site is unchanged.
          </p>
        ) : null}
        <Outlet context={outlet} />
      </section>
    </AdminShell>
  )
}
