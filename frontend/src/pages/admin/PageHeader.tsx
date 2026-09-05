export function PageHeader({
  kicker,
  title,
  description,
}: {
  kicker?: string
  title: string
  description?: string
}) {
  return (
    <div>
      {kicker ? (
        <p className="text-sm font-medium tracking-wide uppercase text-muted-foreground">{kicker}</p>
      ) : null}
      <h1 className="mt-1 text-4xl font-semibold tracking-tight font-display">{title}</h1>
      {description ? <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{description}</p> : null}
    </div>
  )
}
