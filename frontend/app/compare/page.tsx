import { ApiDown, PageHeader } from "@/components/PageHeader";
import { DecisionBadge } from "@/components/DecisionBadge";
import { apiGet } from "@/lib/api";
import { formatMs, formatRatio, formatUsd } from "@/lib/format";
import type { Metrics } from "@/lib/types";

type Side = {
  run_id: string;
  decision: "pass" | "review" | "block";
  candidate: { name: string; version: string };
  candidate_metrics: Metrics;
};

export default async function ComparePage({
  searchParams,
}: {
  searchParams: Promise<{ a?: string; b?: string }>;
}) {
  const query = await searchParams;
  return (
    <div>
      <PageHeader
        title="Compare"
        detail="This page shows two stored runs side by side. It does not create a new release decision."
      />
      <form action="/compare" className="mb-6 flex flex-wrap gap-3">
        <input
          name="a"
          defaultValue={query.a || ""}
          placeholder="Run A"
          className="num rounded border border-[var(--line)] px-2 py-1.5 text-sm"
        />
        <input
          name="b"
          defaultValue={query.b || ""}
          placeholder="Run B"
          className="num rounded border border-[var(--line)] px-2 py-1.5 text-sm"
        />
        <button type="submit" className="rounded-lg bg-[var(--ink)] px-3 py-1.5 text-sm text-[var(--bg)] hover:opacity-90">
          Compare
        </button>
      </form>
      {query.a && query.b ? <Comparison a={query.a} b={query.b} /> : <p className="text-sm text-[var(--muted)]">Choose two run ids.</p>}
    </div>
  );
}

async function Comparison({ a, b }: { a: string; b: string }) {
  const { data, error } = await apiGet<{ note: string; a: Side; b: Side }>(
    `/api/v1/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`,
  );
  if (error || !data) return <ApiDown message={error || "Compare failed"} />;
  return (
    <div>
      <p className="mb-4 text-sm text-[var(--muted)]">{data.note}</p>
      <div className="grid gap-3 md:grid-cols-2">
        <SideCard side={data.a} />
        <SideCard side={data.b} />
      </div>
    </div>
  );
}

function SideCard({ side }: { side: Side }) {
  const metrics = side.candidate_metrics;
  return (
    <section className="panel p-3 text-sm">
      <div className="flex items-center justify-between">
        <h2 className="font-medium">{side.candidate.name}</h2>
        <DecisionBadge decision={side.decision} />
      </div>
      <p className="num mt-1 text-xs text-[var(--muted)]">{side.run_id}</p>
      <dl className="mt-3 space-y-1">
        <div>Accuracy {formatRatio(metrics.accuracy)} ({metrics.passed_cases}/{metrics.completed_cases})</div>
        <div>Median latency {formatMs(metrics.median_latency_ms)}</div>
        <div>p95 latency {formatMs(metrics.p95_latency_ms)}</div>
        <div>Cost {metrics.cost_status === "unavailable" ? "Not measured" : formatUsd(metrics.average_cost_usd)}</div>
        <div>Tool success {formatRatio(metrics.tool_success_rate)}</div>
        <div>Human review {formatRatio(metrics.human_review_rate)}</div>
        <div>Agent failures {metrics.failed_cases}</div>
        <div>Infrastructure {metrics.infrastructure_errors}</div>
        <div>Provider {metrics.provider_errors}</div>
      </dl>
    </section>
  );
}
