import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { QrCode, ScanLine, KeyRound, UserRound } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Spinner } from '@/components/ui/spinner'
import { api, setToken } from '@/services/api'
import { useSession } from '@/store/session'
import { cn } from '@/lib/utils'

type Mode = 'scan' | 'text' | 'quick'

export default function QrLogin({ competitionId }: { competitionId: string }) {
  const nav = useNavigate()
  const fileRef = useRef<HTMLInputElement>(null)
  const [mode, setMode] = useState<Mode>('scan')
  const [fileName, setFileName] = useState('')
  const [qrMessage, setQrMessage] = useState('')
  const [quickId, setQuickId] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const setSession = useSession((s) => s.setSession)

  const isDev = (import.meta.env.VITE_ENABLE_TEST_LOGIN ?? 'true') !== 'false'

  const applyAuth = (res: { token: string; participant: {
    display_name: string
    email: string | null
    vit_registration_number: string | null
    competition_id: string
    already_submitted: boolean
  } }) => {
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
      const res = await api.loginWithQrImage(competitionId, file)
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
      const res = await api.loginWithQrMessage(competitionId, qrMessage.trim())
      applyAuth(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to verify that QR message.')
    } finally {
      setLoading(false)
    }
  }

  const handleQuick = async () => {
    if (!quickId.trim()) {
      setError('Please enter your email, registration number, or display name.')
      return
    }
    if (!competitionId) {
      setError('Competition not available. Please wait or refresh the page.')
      return
    }
    setError('')
    setLoading(true)
    try {
      const res = await api.loginWithTest(competitionId, quickId.trim())
      applyAuth(res)
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : 'Unable to log in with that identifier. Make sure you are in development mode.',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card id="participant-signin" className="w-full max-w-md border-border shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <QrCode className="h-5 w-5" /> Participant sign in
        </CardTitle>
        <CardDescription>
          Use the QR code from your registration to sign in and submit your prompts.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className={cn('flex flex-wrap rounded-lg border border-border bg-muted p-1')}>
          <button
            type="button"
            onClick={() => setMode('scan')}
            className={cn(
              'flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors',
              mode === 'scan' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground',
            )}
          >
            <ScanLine className="h-4 w-4" /> Scan QR
          </button>
          <button
            type="button"
            onClick={() => setMode('text')}
            className={cn(
              'flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors',
              mode === 'text' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground',
            )}
          >
            <KeyRound className="h-4 w-4" /> Paste message
          </button>
          {isDev ? (
            <button
              type="button"
              onClick={() => setMode('quick')}
              className={cn(
                'flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                mode === 'quick' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground',
              )}
            >
              <UserRound className="h-4 w-4" /> Quick login
            </button>
          ) : null}
        </div>

        {mode === 'scan' ? (
          <div className="space-y-4">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={loading}
              className="flex w-full flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed border-border bg-muted/40 px-4 py-10 text-center transition-colors hover:border-foreground/30 disabled:opacity-50"
            >
              {loading ? (
                <Spinner className="h-6 w-6" />
              ) : (
                <ScanLine className="h-8 w-8 text-muted-foreground" />
              )}
              {fileName ? (
                <span className="text-sm font-medium">{fileName}</span>
              ) : (
                <span className="text-sm text-muted-foreground">
                  Tap to upload your QR code image
                </span>
              )}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0])}
            />
          </div>
        ) : mode === 'text' ? (
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="qr-message">QR message</Label>
              <Input
                id="qr-message"
                placeholder="Paste the message from your QR code"
                value={qrMessage}
                onChange={(e) => setQrMessage(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleText()}
                disabled={loading}
              />
            </div>
            <Button
              className="w-full"
              size="lg"
              onClick={handleText}
              disabled={loading || !qrMessage.trim()}
            >
              {loading ? <Spinner className="h-4 w-4" /> : 'Continue'}
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="quick-id">Email, reg number, or name</Label>
              <Input
                id="quick-id"
                placeholder="e.g. test@example.com or TEST001"
                value={quickId}
                onChange={(e) => setQuickId(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleQuick()}
                disabled={loading}
              />
              <p className="text-xs text-muted-foreground">
                Dev-only fallback when your QR isn't available. Use the test participant to try
                the system end-to-end.
              </p>
            </div>
            <Button
              className="w-full"
              size="lg"
              onClick={handleQuick}
              disabled={loading || !quickId.trim()}
            >
              {loading ? <Spinner className="h-4 w-4" /> : 'Sign in'}
            </Button>
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
