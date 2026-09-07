import { useOutletContext } from 'react-router-dom'
import { useState } from 'react'
import { Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { api, getAdminToken } from '@/services/api'
import { Banner } from './Banner'
import { API_BASE, CATEGORIES } from './constants'
import type { AdminOutletContext } from './context'
import { PageHeader } from './PageHeader'

export default function ExportPage() {
  const { competitionId, testMode } = useOutletContext<AdminOutletContext>()
  const [error, setError] = useState('')
  const [note, setNote] = useState('')

  const open = (url: string) => {
    const token = getAdminToken()
    setError('')
    setNote('')
    fetch(`${API_BASE}${url}`, { headers: { Authorization: `Bearer ${token ?? ''}` } })
      .then(async (res) => {
        if (!res.ok) {
          let message = 'Export failed'
          try {
            const body = (await res.json()) as { detail?: string }
            if (typeof body.detail === 'string') message = body.detail
          } catch {
            /* ignore */
          }
          throw new Error(message)
        }
        const header = res.headers.get('Content-Disposition') || ''
        const match = /filename="([^"]+)"/.exec(header)
        const filename = match?.[1] || 'prompts.csv'
        const blob = await res.blob()
        return { blob, filename }
      })
      .then(({ blob, filename }) => {
        const link = window.document.createElement('a')
        const objectUrl = window.URL.createObjectURL(blob)
        link.href = objectUrl
        link.download = filename
        link.click()
        window.URL.revokeObjectURL(objectUrl)
        setNote('Download started.')
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Export failed.'))
  }

  return (
    <div className="space-y-8">
      <PageHeader
        kicker={testMode ? 'Test dataset' : 'Live data'}
        title="Export"
        description="CSV of submitted prompts: event registration number, name, category, prompt. Walk-in test accounts are omitted."
      />
      <Banner message={error} onDismiss={() => setError('')} />
      <Banner message={note} onDismiss={() => setNote('')} tone="note" />
      <Button onClick={() => open(api.adminExportUrl(competitionId))}>
        <Download className="mr-1 h-4 w-4" /> Export all categories
      </Button>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {CATEGORIES.map((c) => (
          <button
            key={c.n}
            type="button"
            onClick={() => open(api.adminExportUrl(competitionId, c.n))}
            className="flex items-center justify-between rounded-lg border border-border p-5 text-left hover:border-foreground/40"
          >
            <span className="block text-sm font-medium">
              {c.n}. {c.label}
            </span>
            <Download className="h-4 w-4 text-muted-foreground" />
          </button>
        ))}
      </div>
    </div>
  )
}
