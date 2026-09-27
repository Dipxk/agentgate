export default function Loading() {
  return (
    <div className="space-y-3" aria-hidden="true">
      <div className="h-6 w-36 rounded-lg bg-[var(--surface)]" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="panel h-16" />
        <div className="panel h-16" />
        <div className="panel h-16" />
        <div className="panel h-16" />
      </div>
      <div className="panel h-56" />
    </div>
  );
}
