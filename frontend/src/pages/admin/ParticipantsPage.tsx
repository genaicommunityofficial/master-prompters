import { useCallback, useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { RefreshCw, UserPlus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Spinner } from '@/components/ui/spinner'
import { api } from '@/services/api'
import type { ParticipantRoster } from '@/types'
import { Banner } from './Banner'
import type { AdminOutletContext } from './context'
import { PageHeader } from './PageHeader'

export default function ParticipantsPage() {
  const { token, competitionId, testMode } = useOutletContext<AdminOutletContext>()
  const [roster, setRoster] = useState<ParticipantRoster | null>(null)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [regNumber, setRegNumber] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [adding, setAdding] = useState(false)

  const load = useCallback(async () => {
    setBusy(true)
    try {
      setRoster(await api.adminParticipants(competitionId, token))
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load participants.')
    } finally {
      setBusy(false)
    }
  }, [token, competitionId])

  useEffect(() => {
    void load()
  }, [load])

  const handleAdd = async () => {
    if (!regNumber.trim()) {
      setError('Registration number is required.')
      return
    }
    setAdding(true)
    try {
      await api.adminCreateRegistration(
        competitionId,
        {
          registration_number: regNumber.trim(),
          display_name: displayName.trim() || undefined,
          email: email.trim() || undefined,
        },
        token,
      )
      setNote(`Added ${regNumber.trim()} to pc_participants. Not written to registrations.`)
      setRegNumber('')
      setDisplayName('')
      setEmail('')
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not add participant.')
    } finally {
      setAdding(false)
    }
  }

  const showLogin = Boolean(roster?.show_login)

  return (
    <div className="space-y-8">
      <PageHeader
        kicker={testMode ? 'Test dataset' : 'Live event'}
        title="Participants"
        description={
          testMode
            ? 'Synthetic dataset users. Login status is not shown.'
            : 'Event registrations (read-only) plus numbers you add here. Same row shows whether they have logged in.'
        }
      />
      <Banner message={error} onDismiss={() => setError('')} />
      <Banner message={note} onDismiss={() => setNote('')} tone="note" />

      <div className="flex justify-end">
        <Button size="sm" variant="outline" onClick={() => void load()} disabled={busy}>
          {busy ? <Spinner className="h-4 w-4" /> : <RefreshCw className="h-4 w-4" />} Refresh
        </Button>
      </div>

      {roster ? (
        <p className="text-sm text-muted-foreground">
          {roster.registered} listed
          {showLogin ? ` · ${roster.logged_in ?? 0} logged in` : ''}
          {' · '}
          {roster.submitted} submitted
        </p>
      ) : null}

      {testMode ? null : (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <UserPlus className="h-4 w-4" /> Add a registration number
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="mb-4 text-sm text-muted-foreground">
              Writes to this competition’s participant list only. The event <code>registrations</code> table is never modified.
            </p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="space-y-1.5">
                <Label htmlFor="reg-num">Registration number</Label>
                <Input id="reg-num" value={regNumber} onChange={(e) => setRegNumber(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="reg-name">Name</Label>
                <Input id="reg-name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="reg-email">Email</Label>
                <Input id="reg-email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              <div className="flex items-end">
                <Button onClick={() => void handleAdd()} disabled={adding || !regNumber.trim()}>
                  {adding ? <Spinner className="h-4 w-4" /> : <UserPlus className="h-4 w-4" />}
                  Add
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-0">
          {!roster ? (
            <p className="px-5 py-8 text-sm text-muted-foreground">Loading…</p>
          ) : roster.participants.length === 0 ? (
            <p className="px-5 py-8 text-sm text-muted-foreground">No participants in this view.</p>
          ) : (
            <div className="overflow-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase text-muted-foreground">
                  <tr className="border-b border-border">
                    <th className="px-5 py-3 font-medium">Name</th>
                    <th className="px-5 py-3 font-medium">Reg. no.</th>
                    <th className="px-5 py-3 font-medium">Source</th>
                    {showLogin ? <th className="px-5 py-3 font-medium">Logged in</th> : null}
                    <th className="px-5 py-3 font-medium">Submitted</th>
                  </tr>
                </thead>
                <tbody>
                  {roster.participants.map((row) => (
                    <tr key={row.id} className="border-b border-border/60 last:border-0">
                      <td className="px-5 py-3">{row.display_name ?? '—'}</td>
                      <td className="px-5 py-3 tabular-nums">{row.registration_number ?? '—'}</td>
                      <td className="px-5 py-3 capitalize text-muted-foreground">{row.source}</td>
                      {showLogin ? (
                        <td className="px-5 py-3">
                          {row.logged_in ? 'Yes' : 'No'}
                          {row.last_login_at ? (
                            <span className="ml-2 text-xs text-muted-foreground">
                              {new Date(row.last_login_at).toLocaleString()}
                            </span>
                          ) : null}
                        </td>
                      ) : null}
                      <td className="px-5 py-3">{row.submitted ? row.submission_status ?? 'Yes' : 'No'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
