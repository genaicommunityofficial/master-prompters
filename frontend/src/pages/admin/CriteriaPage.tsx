import { useCallback, useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { Copy, Eye, FileText, Upload, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
import { api } from '@/services/api'
import type { CriteriaEntry } from '@/types'
import { Banner } from './Banner'
import { CATEGORIES } from './constants'
import type { AdminOutletContext } from './context'
import { PageHeader } from './PageHeader'

export default function CriteriaPage() {
  const { token, competitionId, testMode } = useOutletContext<AdminOutletContext>()
  const [entries, setEntries] = useState<CriteriaEntry[]>([])
  const [preview, setPreview] = useState<{ category: number; md: string } | null>(null)
  const [busyCategory, setBusyCategory] = useState<number | null>(null)
  const [copyBusy, setCopyBusy] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')

  const load = useCallback(async () => {
    try {
      setEntries(await api.adminCriteriaList(competitionId, token))
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load criteria.')
    }
  }, [token, competitionId])

  useEffect(() => {
    void load()
  }, [load])

  const getEntry = (n: number) => entries.find((e) => e.question_number === n)

  const handleUpload = async (n: number, file: File) => {
    setBusyCategory(n)
    try {
      await api.adminCriteriaUpload(competitionId, n, file, token)
      setNote(`Criteria uploaded for category ${n}. Used on the next evaluation run.`)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not upload criteria.')
    } finally {
      setBusyCategory(null)
    }
  }

  const handlePreview = async (n: number) => {
    try {
      const d = await api.adminCriteriaDetail(competitionId, n, token)
      setPreview({ category: n, md: d.content_md })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load criteria.')
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
        description="One markdown rubric per category, injected into Gemini on the next eval run."
      />
      <Banner message={error} onDismiss={() => setError('')} />
      <Banner message={note} onDismiss={() => setNote('')} tone="note" />
      {testMode ? (
        <Button size="sm" variant="outline" onClick={() => void handleCopy()} disabled={copyBusy}>
          {copyBusy ? <Spinner className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          Copy live rubrics to test
        </Button>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileText className="h-4 w-4" /> Per-category markdown
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {CATEGORIES.map((c) => {
              const entry = getEntry(c.n)
              return (
                <div key={c.n} className="rounded-lg border border-border p-5">
                  <div className="text-sm font-medium">
                    {c.n}. {c.label}
                  </div>
                  <div className="mt-2 text-xs text-muted-foreground">
                    {entry ? (
                      <>
                        {entry.file_name}
                        {entry.updated_at ? ` · ${new Date(entry.updated_at).toLocaleDateString()}` : ''}
                      </>
                    ) : (
                      'No criteria uploaded yet'
                    )}
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:border-foreground/40">
                      {busyCategory === c.n ? <Spinner className="h-3.5 w-3.5" /> : <Upload className="h-3.5 w-3.5" />}
                      {busyCategory === c.n ? 'Uploading…' : 'Upload .md'}
                      <input
                        type="file"
                        accept=".md,.markdown,text/markdown"
                        className="sr-only"
                        disabled={busyCategory !== null}
                        onChange={(e) => {
                          const f = e.target.files?.[0]
                          if (f) void handleUpload(c.n, f)
                          e.target.value = ''
                        }}
                      />
                    </label>
                    {entry ? (
                      <Button size="sm" variant="outline" onClick={() => void handlePreview(c.n)}>
                        <Eye className="h-3.5 w-3.5" /> Preview
                      </Button>
                    ) : null}
                  </div>
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>
      {preview ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between text-base">
              <span>Category {preview.category}: criteria preview</span>
              <Button size="sm" variant="outline" onClick={() => setPreview(null)}>
                <X className="h-4 w-4" /> Close
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-md border border-border bg-muted/40 p-4 font-mono text-xs leading-relaxed">
              {preview.md || 'No content.'}
            </pre>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
