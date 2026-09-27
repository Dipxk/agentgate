import { decisionLabel } from "@/lib/format";

const STYLES: Record<string, string> = {
  pass: "bg-[#143024] text-[#7ddea8]",
  review: "bg-[#332816] text-[#f0c36a]",
  block: "bg-[#3a1c1c] text-[#f3b0aa]",
};

export function DecisionBadge({
  decision,
  inconclusive = false,
}: {
  decision: string;
  inconclusive?: boolean;
}) {
  const style = STYLES[decision] || "bg-[var(--hover)] text-[var(--muted)]";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${style}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {decisionLabel(decision, inconclusive)}
    </span>
  );
}
