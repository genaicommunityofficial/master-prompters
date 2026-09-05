import { Link } from 'react-router-dom'
import { CheckCircle2 } from 'lucide-react'
import { PageShell } from '@/components/layout'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useSession } from '@/store/session'

export default function SubmittedPage() {
  const name = useSession((s) => s.displayName)

  return (
    <PageShell>
      <section className="container flex min-h-[60vh] items-center justify-center py-16">
        <Card className="w-full max-w-md text-center">
          <CardContent className="flex flex-col items-center gap-4 pt-10">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-emerald-600/10 text-emerald-600">
              <CheckCircle2 className="h-8 w-8" />
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-balance">
              Received
            </h1>
            <p className="text-muted-foreground leading-relaxed">
              {name ? `${name}.` : 'Thank you.'}
            </p>
            <div className="mt-2 flex flex-col gap-2 sm:flex-row">
              <Button asChild variant="outline" className="sm:w-auto w-full">
                <Link to="/leaderboard">Results</Link>
              </Button>
              <Button asChild className="sm:w-auto w-full">
                <Link to="/">Home</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </section>
    </PageShell>
  )
}