import { ApiDown, PageHeader } from "@/components/PageHeader";
import { RunTable } from "@/components/RunTable";
import { apiGet } from "@/lib/api";
import { formatMs, formatRatio, formatUsd } from "@/lib/format";
import type { Overview } from "@/lib/types";

export default async function OverviewPage() {
  const { data, error } = await apiGet<Overview>("/api/v1/overview");
  if (error || !data) return <ApiDown message={error || "No data"} />;

  const stats = [
    ["Projects", String(data.projects)],
    ["Runs", String(data.runs)],
    ["Pass", String(data.decisions.pass)],
    ["Review", String(data.decisions.review)],
    ["Block", String(data.decisions.block)],
    ["Mean accuracy", formatRatio(data.mean_candidate_accuracy)],
    ["Mean median latency", formatMs(data.mean_candidate_median_latency_ms)],
    [
      "Mean cost",
      data.cost_runs_measured === 0 ? "Not measured" : formatUsd(data.mean_candidate_cost_usd),
    ],
  ];

  return (
    <div>
      <PageHeader
        title="Overview"
        detail="Averages use stored candidate measurements. Missing costs stay missing. Infrastructure failures are not folded into accuracy."
      />
      <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {stats.map(([label, value]) => (
          <div key={label} className="panel stat px-4 py-3">
            <dt className="flex items-center gap-2 text-xs text-[var(--muted)]">
              <Dot label={label} />
              {label}
            </dt>
            <dd className="num mt-1.5 text-xl tracking-tight">{value}</dd>
          </div>
        ))}
      </dl>
      <section className="mt-8">
        <h2 className="mb-2 text-sm font-semibold">Recent runs</h2>
        <RunTable runs={data.recent_runs} />
      </section>
      <section className="mt-8">
        <h2 className="mb-2 text-sm font-semibold">Blocked releases</h2>
        <RunTable runs={data.regressions} />
      </section>
    </div>
  );
}

function Dot({ label }: { label: string }) {
  const color = label === "Pass" ? "bg-[#3dd68c]" : label === "Review" ? "bg-[#e2b15a]" : label === "Block" ? "bg-[#f07167]" : "bg-[#4b5563]";
  return <span className={`h-1.5 w-1.5 rounded-full ${color}`} />;
}
