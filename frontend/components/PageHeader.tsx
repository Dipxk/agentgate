export function ApiDown({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-[#5c4a28] bg-[#2a220f] px-4 py-3 text-sm">
      <p className="font-medium">API unavailable</p>
      <p className="mt-1 text-[var(--muted)]">{message}</p>
    </div>
  );
}

export function PageHeader({ title, detail }: { title: string; detail?: string }) {
  return (
    <header className="mb-6">
      <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
      {detail ? <p className="mt-1 max-w-3xl text-sm text-[var(--muted)]">{detail}</p> : null}
    </header>
  );
}
