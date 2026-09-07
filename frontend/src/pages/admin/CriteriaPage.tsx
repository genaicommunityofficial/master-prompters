import { useCallback, useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { Copy, Lock, LockOpen, Save } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { api } from '@/services/api'
import type { CriteriaEntry } from '@/types'
import { Banner } from './Banner'
import { CATEGORIES } from './constants'
import type { AdminOutletContext } from './context'
import { PageHeader } from './PageHeader'

const emptyDrafts = (): Record<number, string> =>
  Object.fromEntries(CATEGORIES.map((c) => [c.n, ''])) as Record<number, string>

export default function CriteriaPage() {
  const { token, competitionId, testMode } = useOutletContext<AdminOutletContext>()
  const [entries, setEntries] = useState<CriteriaEntry[]>([])
  const [drafts, setDrafts] = useState<Record<number, string>>(emptyDrafts)
  const [busyCategory, setBusyCategory] = useState<number | null>(null)
  const [copyBusy, setCopyBusy] = useState(false)
  const [pendingUnlock, setPendingUnlock] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')

  const load = useCallback(async () => {
    try {
      const rows = await api.adminCriteriaList(competitionId, token)
      setEntries(rows)
      const next = emptyDrafts()
      for (const row of rows) {
        next[row.question_number] = row.content_md ?? ''
      }
      setDrafts(next)
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load criteria.')
    }
  }, [token, competitionId])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (pendingUnlock == null) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setPendingUnlock(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [pendingUnlock])

  const getEntry = (n: number) => entries.find((e) => e.question_number === n)

  const handleSave = async (n: number) => {
    const text = (drafts[n] || '').trim()
    if (!text) {
      setError('Enter criteria text before saving.')
      return
    }
    setBusyCategory(n)
    try {
      await api.adminCriteriaSave(competitionId, n, text, token)
      setNote(`Saved criteria for category ${n}. Used on the next evaluation run.`)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save criteria.')
    } finally {
      setBusyCategory(null)
    }
  }

  const handleLock = async (n: number) => {
    setBusyCategory(n)
    try {
      await api.adminCriteriaLock(competitionId, n, token)
      setNote(`Locked category ${n}. Unlock to edit again.`)
      setPendingUnlock(null)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not lock criteria.')
    } finally {
      setBusyCategory(null)
    }
  }

  const handleUnlock = async (n: number) => {
    if (pendingUnlock !== n) {
      setPendingUnlock(n)
      return
    }
    setBusyCategory(n)
    try {
      await api.adminCriteriaUnlock(competitionId, n, token)
      setNote(`Unlocked category ${n}. You can edit and save again.`)
      setPendingUnlock(null)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not unlock criteria.')
    } finally {
      setBusyCategory(null)
    }
  }

  const handleCopy = async () => {
    setCopyBusy(true)
    try {
      const res = await api.adminCopyLiveCriteria(competitionId, token)
      setNote(`Copied ${res.copied} rubric${res.copied === 1 ? '' : 's'} from live.`)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not copy live rubrics.')
    } finally {
      setCopyBusy(false)
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        kicker={testMode ? 'Test dataset' : 'Live rubrics'}
        title="Criteria"
        description="Paste one markdown rubric per category, then lock it so it cannot be edited during evaluation."
      />
      <Banner message={error} onDismiss={() => setError('')} />
      <Banner message={note} onDismiss={() => setNote('')} tone="note" />
      {testMode ? (
        <Button size="sm" variant="outline" onClick={() => void handleCopy()} disabled={copyBusy}>
          {copyBusy ? <Spinner className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          Copy live rubrics to test
        </Button>
      ) : null}
      <div className="space-y-4">
        {CATEGORIES.map((c) => {
          const entry = getEntry(c.n)
          const locked = Boolean(entry?.locked)
          const saved = Boolean(entry?.content_md?.trim())
          const busy = busyCategory === c.n
          const confirmingUnlock = pendingUnlock === c.n
          const fieldId = `criteria-${c.n}`
          return (
            <Card key={c.n}>
              <CardHeader>
                <CardTitle className="flex flex-wrap items-center justify-between gap-2 text-base">
                  <span>
                    {c.n}. {c.label}
                    {locked ? (
                      <span className="ml-2 text-xs font-normal uppercase tracking-wide text-muted-foreground">
                        Locked
                      </span>
                    ) : null}
                  </span>
                  {entry?.updated_at ? (
                    <span className="text-xs font-normal text-muted-foreground">
                      Saved {new Date(entry.updated_at).toLocaleString()}
                    </span>
                  ) : (
                    <span className="text-xs font-normal text-muted-foreground">Not saved yet</span>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <Label htmlFor={fieldId} className="sr-only">
                  Criteria for {c.label}
                </Label>
                <Textarea
                  id={fieldId}
                  value={drafts[c.n] ?? ''}
                  onChange={(e) => setDrafts((prev) => ({ ...prev, [c.n]: e.target.value }))}
                  readOnly={locked}
                  disabled={busy}
                  rows={12}
                  className="min-h-[220px] font-mono text-xs"
                  placeholder="Paste judging criteria here. Markdown is fine."
                />
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    onClick={() => void handleSave(c.n)}
                    disabled={busy || locked || !(drafts[c.n] || '').trim()}
                  >
                    {busy ? <Spinner className="h-4 w-4" /> : <Save className="h-4 w-4" />}
                    Save
                  </Button>
                  {locked ? (
                    <>
                      {confirmingUnlock ? (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setPendingUnlock(null)}
                          disabled={busy}
                        >
                          Cancel
                        </Button>
                      ) : null}
                      <Button
                        size="sm"
                        variant={confirmingUnlock ? 'destructive' : 'outline'}
                        onClick={() => void handleUnlock(c.n)}
                        disabled={busy}
                        aria-label={
                          confirmingUnlock ? `Confirm unlock ${c.label}` : `Unlock ${c.label}`
                        }
                      >
                        <LockOpen className="h-4 w-4" />
                        {confirmingUnlock ? 'Confirm unlock' : 'Unlock'}
                      </Button>
                    </>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void handleLock(c.n)}
                      disabled={busy || !saved}
                    >
                      <Lock className="h-4 w-4" />
                      Lock
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
