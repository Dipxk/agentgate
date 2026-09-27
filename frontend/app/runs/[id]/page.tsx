import Link from "next/link";
import { replayRun } from "@/app/actions";
import { DecisionBadge } from "@/components/DecisionBadge";
import { MetricTable } from "@/components/MetricTable";
import { ApiDown, PageHeader } from "@/components/PageHeader";
import { apiGet } from "@/lib/api";
import { formatMs, formatRatio, formatUsd, providerLabel } from "@/lib/format";
import type { Metrics, Rule, RunSummary, Variance, Version } from "@/lib/types";

type CaseRow = {
  case_id: string;
  side: string;
  trial: number;
  status: string;
  failure_class: string | null;
  outcome: string | null;
  latency_ms: number | null;
  cost_usd: number | null;
  cost_status: string;
};

type Comparison = {
  case_id: string;
  baseline_status: string | null;
  candidate_status: string | null;
  change: string;
};

type Report = {
  manifest: {
    run_id: string;
    dataset_name: string;
    dataset_version: string;
    dataset_hash: string;
    evaluator_version: string;
    seed: number | null;
    trials: number;
  };
  gate: { decision: string; inconclusive: boolean; reasons: string[]; rules: Rule[] };
  variance: Variance;
  case_results: CaseRow[];
  comparisons: Comparison[];
  logs: { event: string; ts: string; case_id?: string; status?: string; level?: string }[];
};

type Detail = RunSummary & { report: Report };

export default async function RunPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ status?: string }>;
}) {
  const { id } = await params;
  const query = await searchParams;
  const { data, error } = await apiGet<Detail>(`/api/v1/runs/${id}`);
  if (error || !data) return <ApiDown message={error || "Run not found"} />;
  const report = data.report;
  const filter = query.status;
  const comparisons = report.comparisons.filter((item) => !filter || item.candidate_status === filter || item.change === filter);
  const candidateCases = new Map(
    report.case_results.filter((item) => item.side === "candidate" && item.trial === 1).map((item) => [item.case_id, item]),
  );

  return (
    <div>
      <PageHeader
        title="Evaluation"
        detail={`${report.manifest.dataset_name}@${report.manifest.dataset_version} · dataset ${report.manifest.dataset_hash.slice(0, 12)} · evaluator ${report.manifest.evaluator_version}`}
      />
      <section className="panel relative mb-6 overflow-hidden px-4 py-3.5">
        <span className={`absolute inset-y-0 left-0 w-0.5 ${barClass(report.gate.decision)}`} />
        <div className="flex flex-wrap items-center gap-3">
          <DecisionBadge decision={report.gate.decision} inconclusive={report.gate.inconclusive} />
          <span className="num text-xs text-[var(--muted)]">{report.manifest.run_id}</span>
          <form action={replayRun} className="ml-auto">
            <input type="hidden" name="runId" value={report.manifest.run_id} />
            <button type="submit" className="rounded-lg border border-[var(--line)] bg-[var(--bg)] px-2.5 py-1 text-xs hover:bg-[var(--hover)]">
              Replay run
            </button>
          </form>
        </div>
        <ul className="mt-3 space-y-1 text-sm">
          {report.gate.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </section>
      <div className="mb-6 grid gap-3 md:grid-cols-2">
        <VersionCard title="Production baseline" version={data.baseline} metrics={data.baseline_metrics} />
        <VersionCard title="Candidate" version={data.candidate} metrics={data.candidate_metrics} />
      </div>
      <Counts metrics={data.candidate_metrics} />
      <div className="mt-6">
        <MetricTable rules={report.gate.rules} />
      </div>
      <VariancePanel variance={report.variance} />
      <div className="mb-2 mt-8 flex items-center justify-between">
        <h2 className="text-sm font-semibold">Cases</h2>
        <div className="flex gap-1 text-xs">
          <FilterLink href={`/runs/${id}`} label="All" on={!filter} />
          <FilterLink href={`/runs/${id}?status=failed`} label="Failed" on={filter === "failed"} />
          <FilterLink href={`/runs/${id}?status=regression`} label="Regressions" on={filter === "regression"} />
          <FilterLink href={`/runs/${id}?status=infrastructure_error`} label="Infrastructure" on={filter === "infrastructure_error"} />
        </div>
      </div>
      <div className="panel overflow-x-auto">
        <table className="min-w-[760px] text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-[var(--muted)]">
            <tr>
              <th className="px-3 py-2 font-medium">Case</th>
              <th className="px-3 py-2 font-medium">Change</th>
              <th className="px-3 py-2 font-medium">Candidate status</th>
              <th className="px-3 py-2 font-medium">Outcome</th>
              <th className="px-3 py-2 text-right font-medium">Latency</th>
              <th className="px-3 py-2 text-right font-medium">Cost</th>
            </tr>
          </thead>
          <tbody>
            {comparisons.map((item) => {
              const result = candidateCases.get(item.case_id);
              return (
                <tr key={item.case_id} className="border-t border-[var(--line)]">
                  <td className="px-3 py-2">
                    <Link href={`/runs/${id}/cases/${item.case_id}`} className="font-medium underline decoration-transparent underline-offset-2 hover:decoration-[var(--ink)]">
                      {item.case_id}
                    </Link>
                  </td>
                  <td className="px-3 py-2">{item.change}</td>
                  <td className="px-3 py-2">{result?.status || item.candidate_status}</td>
                  <td className="num px-3 py-2 text-xs">{result?.outcome || "n/a"}</td>
                  <td className="num px-3 py-2 text-right">{formatMs(result?.latency_ms)}</td>
                  <td className="num px-3 py-2 text-right">
                    {result?.cost_status === "measured" ? formatUsd(result.cost_usd) : "Not measured"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <h2 className="mb-2 mt-8 text-sm font-semibold">Log</h2>
      <pre className="panel max-h-80 overflow-auto p-3 text-xs leading-5">
        {report.logs
          .map((entry) =>
            [entry.ts, entry.level || "info", entry.event, entry.case_id || "", entry.status || ""].filter(Boolean).join("  "),
          )
          .join("\n")}
      </pre>
    </div>
  );
}

function barClass(decision: string): string {
  if (decision === "block") return "bg-[#cf222e]";
  if (decision === "review") return "bg-[#9a6700]";
  if (decision === "pass") return "bg-[#1a7f37]";
  return "bg-[var(--line)]";
}

function FilterLink({ href, label, on }: { href: string; label: string; on: boolean }) {
  return (
    <Link
      href={href}
      className={`rounded-full px-2.5 py-1 ${on ? "bg-[var(--surface)] font-medium shadow-[var(--shadow)]" : "text-[var(--muted)] hover:bg-[var(--hover)]"}`}
    >
      {label}
    </Link>
  );
}

function VersionCard({
  title,
  version,
  metrics,
}: {
  title: string;
  version: Version | null;
  metrics: Metrics | null;
}) {
  return (
    <section className="panel p-4">
      <h2 className="text-xs uppercase tracking-wide text-[var(--muted)]">{title}</h2>
      {version ? (
        <div className="mt-2 text-sm">
          <div className="font-medium">{version.name}</div>
          <p className="text-[var(--muted)]">
            {version.version} · {providerLabel(version.provider_class)} · {version.provider}
          </p>
          <p className="num mt-1 text-xs text-[var(--muted)]">config {version.config_hash.slice(0, 12)}</p>
          {version.commit ? <p className="num text-xs">commit {version.commit}</p> : null}
          <p className="mt-2">Accuracy {formatRatio(metrics?.accuracy)} ({metrics?.passed_cases ?? 0}/{metrics?.completed_cases ?? 0} completed)</p>
        </div>
      ) : (
        <p className="mt-2 text-sm text-[var(--muted)]">No baseline was recorded.</p>
      )}
    </section>
  );
}

function Counts({ metrics }: { metrics: Metrics }) {
  const items = [
    ["Agent failures", String(metrics.failed_cases)],
    ["Infrastructure errors", String(metrics.infrastructure_errors)],
    ["Provider errors", String(metrics.provider_errors)],
    ["Completed", String(metrics.completed_cases)],
  ];
  return (
    <div>
      <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {items.map(([label, value]) => (
          <div key={label} className="panel px-3 py-2.5">
            <dt className="text-xs text-[var(--muted)]">{label}</dt>
            <dd className="num text-lg">{value}</dd>
          </div>
        ))}
      </dl>
      {metrics.infrastructure_errors + metrics.provider_errors > 0 ? (
        <p className="mt-2 text-xs text-[var(--muted)]">
          Infrastructure and provider errors are excluded from accuracy. They are not scored as 0.
        </p>
      ) : null}
    </div>
  );
}

function VariancePanel({ variance }: { variance: Variance }) {
  return (
    <section className="panel mt-6 p-4 text-sm">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold">Trials</h2>
        {variance.sufficient ? null : (
          <span className="rounded-full bg-[var(--hover)] px-2 py-0.5 text-xs text-[var(--muted)]">Insufficient trials</span>
        )}
      </div>
      <p className="mt-2">
        {variance.trials} stored, {variance.min_trials} required before the badge clears. Mean {formatRatio(variance.mean_accuracy)}.
        Median {formatRatio(variance.median_accuracy)}. Sample variance{" "}
        {variance.sample_variance === null ? "not computed" : variance.sample_variance.toFixed(6)}.
      </p>
      <p className="mt-1 text-xs text-[var(--muted)]">{variance.note}</p>
    </section>
  );
}
