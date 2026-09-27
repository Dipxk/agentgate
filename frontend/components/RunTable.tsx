import Link from "next/link";
import { DecisionBadge } from "./DecisionBadge";
import { formatMs, formatRatio, formatUsd } from "@/lib/format";
import type { RunSummary } from "@/lib/types";

export function RunTable({ runs }: { runs: RunSummary[] }) {
  if (runs.length === 0) {
    return <p className="text-sm text-[var(--muted)]">No evaluation runs stored.</p>;
  }
  return (
    <div className="panel overflow-x-auto">
      <table className="min-w-[760px] text-sm">
        <thead className="text-left text-xs uppercase tracking-wide text-[var(--muted)]">
          <tr>
            <th className="px-3 py-2 font-medium">Run</th>
            <th className="px-3 py-2 font-medium">Candidate</th>
            <th className="px-3 py-2 text-right font-medium">Accuracy</th>
            <th className="px-3 py-2 text-right font-medium">Median latency</th>
            <th className="px-3 py-2 text-right font-medium">Cost</th>
            <th className="px-3 py-2 font-medium">Decision</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id} className="border-t border-[var(--line)]">
              <td className="px-3 py-2">
                <Link href={`/runs/${run.id}`} className="num font-medium underline decoration-transparent underline-offset-2 hover:decoration-[var(--ink)]">
                  {run.id.slice(0, 12)}
                </Link>
                <div className="text-xs text-[var(--muted)]">{run.started_at.replace("T", " ").slice(0, 19)} UTC</div>
              </td>
              <td className="px-3 py-2">
                <div>{run.candidate.name}</div>
                <div className="text-xs text-[var(--muted)]">{run.candidate.version}</div>
                {run.reasons[0] ? <p className="mt-1 max-w-sm text-xs leading-5 text-[var(--muted)]">{run.reasons[0]}</p> : null}
              </td>
              <td className="num px-3 py-2 text-right">
                {formatRatio(run.candidate_metrics.accuracy)}
                <div className="text-xs text-[var(--muted)]">
                  {run.candidate_metrics.passed_cases}/{run.candidate_metrics.completed_cases || 0}
                </div>
              </td>
              <td className="num px-3 py-2 text-right">{formatMs(run.candidate_metrics.median_latency_ms)}</td>
              <td className="num px-3 py-2 text-right">
                {run.candidate_metrics.cost_status === "unavailable"
                  ? "Not measured"
                  : formatUsd(run.candidate_metrics.average_cost_usd)}
              </td>
              <td className="px-3 py-2">
                <DecisionBadge decision={run.decision} inconclusive={run.inconclusive} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
