import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ScanLine, KeyRound, ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Spinner } from '@/components/ui/spinner'
import { api, setToken } from '@/services/api'
import { useSession } from '@/store/session'
import { cn } from '@/lib/utils'
import type { AuthResponse } from '@/types'

type Step = 'reg' | 'qr'
type QrMode = 'scan' | 'text'

export default function QrLogin({ competitionId }: { competitionId: string }) {
  const nav = useNavigate()
  const fileRef = useRef<HTMLInputElement>(null)
  const [step, setStep] = useState<Step>('reg')
  const [qrMode, setQrMode] = useState<QrMode>('scan')
  const [fileName, setFileName] = useState('')
  const [qrMessage, setQrMessage] = useState('')
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
      if (!res.requires_qr && res.token && res.participant) {
        applyAuth({ token: res.token, participant: res.participant })
        return
      }
      setStep('qr')
    } catch (e) {
      setError(
        e instanceof Error ? e.message : 'Unable to look up that registration number.',
      )
    } finally {
      setLoading(false)
    }
  }

  const handleFile = async (file: File | undefined) => {
    if (!file) return
    if (!competitionId) {
      setError('Competition not available. Please wait or refresh the page.')
      return
    }
    setFileName(file.name)
    setError('')
    setLoading(true)
    try {
      const res = await api.loginWithQrImage(competitionId, regNumber.trim(), file)
      applyAuth(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to verify that QR code.')
    } finally {
      setLoading(false)
    }
  }

  const handleText = async () => {
    if (!qrMessage.trim()) {
      setError('Please paste your QR message or scan your QR code.')
      return
    }
    if (!competitionId) {
      setError('Competition not available. Please wait or refresh the page.')
      return
    }
    setError('')
    setLoading(true)
    try {
      const res = await api.loginWithQrMessage(competitionId, regNumber.trim(), qrMessage.trim())
      applyAuth(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to verify that QR message.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card id="participant-signin" className="w-full max-w-md border-border shadow-sm">
      <CardHeader>
        <CardTitle>Enter</CardTitle>
        <CardDescription>
          {step === 'reg' ? 'Registration number' : regNumber.trim()}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {step === 'reg' ? (
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
            <Button className="w-full" size="lg" onClick={() => void handleReg()} disabled={loading || !regNumber.trim()}>
              {loading ? <Spinner className="h-4 w-4" /> : 'Continue'}
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            <button
              type="button"
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              onClick={() => {
                setStep('reg')
                setError('')
              }}
            >
              <ArrowLeft className="h-3.5 w-3.5" /> Change registration number
            </button>
            <div className={cn('flex rounded-lg border border-border bg-muted p-1')}>
              <button
                type="button"
                onClick={() => setQrMode('scan')}
                className={cn(
                  'flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium',
                  qrMode === 'scan' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground',
                )}
              >
                <ScanLine className="h-4 w-4" /> Scan QR
              </button>
              <button
                type="button"
                onClick={() => setQrMode('text')}
                className={cn(
                  'flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium',
                  qrMode === 'text' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground',
                )}
              >
                <KeyRound className="h-4 w-4" /> Paste message
              </button>
            </div>

            {qrMode === 'scan' ? (
              <div>
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  disabled={loading}
                  className="flex w-full flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed border-border bg-muted/40 px-4 py-10 text-center hover:border-foreground/30 disabled:opacity-50"
                >
                  {loading ? (
                    <Spinner className="h-6 w-6" />
                  ) : (
                    <ScanLine className="h-8 w-8 text-muted-foreground" />
                  )}
                  {fileName ? (
                    <span className="text-sm font-medium">{fileName}</span>
                  ) : (
                    <span className="text-sm text-muted-foreground">Tap to upload your QR code image</span>
                  )}
                </button>
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => void handleFile(e.target.files?.[0])}
                />
              </div>
            ) : (
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label htmlFor="qr-message">QR message</Label>
                  <Input
                    id="qr-message"
                    placeholder="Paste the message from your QR code"
                    value={qrMessage}
                    onChange={(e) => setQrMessage(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && void handleText()}
                    disabled={loading}
                  />
                </div>
                <Button
                  className="w-full"
                  size="lg"
                  onClick={() => void handleText()}
                  disabled={loading || !qrMessage.trim()}
                >
                  {loading ? <Spinner className="h-4 w-4" /> : 'Sign in'}
                </Button>
              </div>
            )}
          </div>
        )}

        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}
