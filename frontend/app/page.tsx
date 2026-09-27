import { runEvaluation } from "@/app/actions";
import { ApiDown, PageHeader } from "@/components/PageHeader";
import { RunTable } from "@/components/RunTable";
import { apiGet } from "@/lib/api";
import { formatMs, formatRatio, formatUsd } from "@/lib/format";
import type { Overview } from "@/lib/types";

const CHANGE: Record<string, string> = {
  regressed: "Approves returns after 30 days",
  fixed: "Treats day 30 as allowed and refuses later returns",
  cautious: "Keeps that fix and asks a human more often",
};

type Version = { name: string; path: string; role: string };
type Project = { id: string; config: { versions?: Version[] } };

export default async function OverviewPage() {
  const { data, error } = await apiGet<Overview>("/api/v1/overview");
  if (error || !data) return <ApiDown message={error || "No data"} />;
  const projects = await apiGet<Project[]>("/api/v1/projects");
  const project = projects.data?.[0];
  const versions = project?.config.versions || [];
  const production = versions.find((item) => item.role === "production");
  const candidates = [...versions.filter((item) => item.role !== "production")].sort(
    (a, b) => order(a.name) - order(b.name),
  );

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
        title="Release check"
        detail="A change is run on the same cases as the agent already in production. Pass means it stayed inside the gates. Block means behavior got worse. Review means a person should look before it ships."
      />
      {project && production && candidates.length > 0 ? (
        <form action={runEvaluation} className="panel mb-8 p-4">
          <h2 className="text-sm font-semibold">Run a check</h2>
          <p className="mt-1 max-w-2xl text-sm text-[var(--muted)]">
            Production is {production.name}. Pick a change to the support agent. It is scored on the same cases when you run it. The numbers below are from earlier runs, not from this button.
          </p>
          <div className="mt-4 flex flex-wrap items-end gap-3">
            <input type="hidden" name="projectId" value={project.id} />
            <input type="hidden" name="baseline" value={production.path} />
            <input type="hidden" name="trials" value="1" />
            <label className="min-w-[280px] flex-1 text-xs text-[var(--muted)]">
              Change
              <select name="candidate" className="mt-1 w-full rounded-lg border border-[var(--line)] px-2 py-2 text-sm text-[var(--ink)]">
                {candidates.map((version) => (
                  <option key={version.path} value={version.path}>
                    {CHANGE[version.name] || version.name}
                  </option>
                ))}
              </select>
            </label>
            <button type="submit" className="rounded-lg bg-[var(--ink)] px-3 py-2 text-sm text-[var(--bg)] hover:opacity-90">
              Run check
            </button>
          </div>
        </form>
      ) : null}
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

function order(name: string): number {
  const rank = ["regressed", "fixed", "cautious"].indexOf(name);
  return rank === -1 ? 99 : rank;
}

function Dot({ label }: { label: string }) {
  const color = label === "Pass" ? "bg-[#3dd68c]" : label === "Review" ? "bg-[#e2b15a]" : label === "Block" ? "bg-[#f07167]" : "bg-[#4b5563]";
  return <span className={`h-1.5 w-1.5 rounded-full ${color}`} />;
}
