import { formatDelta, formatMetric } from "@/lib/format";
import type { Rule } from "@/lib/types";

const MARK: Record<string, string> = {
  pass: "bg-[#143024] text-[#7ddea8]",
  review: "bg-[#332816] text-[#f0c36a]",
  block: "bg-[#3a1c1c] text-[#f3b0aa]",
  skipped: "bg-[var(--hover)] text-[var(--muted)]",
  not_measured: "bg-[var(--hover)] text-[var(--muted)]",
};

const LABEL: Record<string, string> = {
  pass: "Pass",
  review: "Review",
  block: "Block",
  skipped: "Skip",
  not_measured: "n/a",
};

export function MetricTable({ rules }: { rules: Rule[] }) {
  return (
    <div className="panel overflow-x-auto">
      <table className="min-w-[720px] text-sm">
        <thead className="text-left text-xs uppercase tracking-wide text-[var(--muted)]">
          <tr>
            <th className="px-3 py-2 font-medium">Metric</th>
            <th className="px-3 py-2 text-right font-medium">Production</th>
            <th className="px-3 py-2 text-right font-medium">Candidate</th>
            <th className="px-3 py-2 text-right font-medium">Change</th>
            <th className="px-3 py-2 font-medium">Gate</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((rule) => (
            <tr key={rule.metric} className="border-t border-[var(--line)] align-top">
              <td className="px-3 py-2.5">
                <div className="font-medium">{rule.label}</div>
                {rule.status === "pass" ? null : (
                  <div className="mt-0.5 max-w-md text-xs leading-5 text-[var(--muted)]">{rule.detail}</div>
                )}
              </td>
              <td className="num px-3 py-2.5 text-right">{formatMetric(rule, rule.baseline)}</td>
              <td className="num px-3 py-2.5 text-right">{formatMetric(rule, rule.candidate)}</td>
              <td className="num px-3 py-2.5 text-right">{formatDelta(rule)}</td>
              <td className="px-3 py-2.5">
                <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${MARK[rule.status] || ""}`}>
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />
                  {LABEL[rule.status] || rule.status}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
