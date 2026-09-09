import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Spinner } from '@/components/ui/spinner'
import { api, setToken } from '@/services/api'
import { useSession } from '@/store/session'
import type { AuthResponse } from '@/types'

export default function QrLogin({ competitionId }: { competitionId: string }) {
  const nav = useNavigate()
  const [regNumber, setRegNumber] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const setSession = useSession((s) => s.setSession)

  const applyAuth = (res: AuthResponse) => {
    setToken(res.token)
    setSession({
      token: res.token,
      displayName: res.participant.display_name,
      email: res.participant.email,
      vitReg: res.participant.vit_registration_number,
      competitionId: res.participant.competition_id,
      role: 'participant',
    })
    nav(res.participant.already_submitted ? '/submitted' : '/competition')
  }

  const handleReg = async () => {
    if (!regNumber.trim()) {
      setError('Please enter your registration number.')
      return
    }
    if (!competitionId) {
      setError('Competition not available. Please wait or refresh the page.')
      return
    }
    setError('')
    setLoading(true)
    try {
      const res = await api.loginWithRegistrationNumber(competitionId, regNumber.trim())
      if (res.token && res.participant) {
        applyAuth({ token: res.token, participant: res.participant })
        return
      }
      setError('Could not sign in with that registration number.')
    } catch (e) {
      setError(
        e instanceof Error ? e.message : 'Unable to look up that registration number.',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card id="participant-signin" className="w-full max-w-md border-border shadow-sm">
      <CardHeader>
        <CardTitle>Enter</CardTitle>
        <CardDescription>Registration number</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="reg-number">Registration number</Label>
            <Input
              id="reg-number"
              autoComplete="off"
              placeholder="e.g. 23BCE0001"
              value={regNumber}
              onChange={(e) => setRegNumber(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && void handleReg()}
              disabled={loading}
            />
          </div>
          <Button
            type="button"
            className="w-full"
            size="lg"
            onClick={() => void handleReg()}
            disabled={loading || !regNumber.trim()}
          >
            {loading ? <Spinner className="h-4 w-4" /> : 'Sign in'}
          </Button>
        </div>

        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}
