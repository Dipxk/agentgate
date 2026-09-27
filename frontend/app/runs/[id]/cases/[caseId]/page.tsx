import Link from "next/link";
import { ApiDown, PageHeader } from "@/components/PageHeader";
import { apiGet } from "@/lib/api";
import { formatMs, formatUsd } from "@/lib/format";

type ToolCall = {
  name: string;
  arguments: Record<string, unknown>;
  result: unknown;
  latency_ms: number;
  error: string | null;
};

type Evaluator = {
  evaluator: string;
  kind: "deterministic" | "subjective";
  status: string;
  detail: string;
};

type Side = {
  status: string;
  failure_class: string | null;
  case_input: string | null;
  output: string | null;
  outcome: string | null;
  expected_outcome: string | null;
  expected_output: string | null;
  must_call: string[];
  must_not_call: string[];
  tool_calls: ToolCall[];
  evaluator_results: Evaluator[];
  latency_ms: number | null;
  model_latency_ms: number | null;
  tool_latency_ms: number | null;
  evaluation_latency_ms: number | null;
  cost_usd: number | null;
  cost_status: string;
  error: string | null;
};

export default async function CasePage({ params }: { params: Promise<{ id: string; caseId: string }> }) {
  const { id, caseId } = await params;
  const { data, error } = await apiGet<{
    case_id: string;
    comparison: { change: string } | null;
    baseline: Side | null;
    candidate: Side | null;
  }>(`/api/v1/runs/${id}/cases/${caseId}`);
  if (error || !data) return <ApiDown message={error || "Case not found"} />;
  const input = data.candidate?.case_input || data.baseline?.case_input || "Not stored";
  const expected = data.candidate || data.baseline;

  return (
    <div>
      <PageHeader title={data.case_id} detail={data.comparison ? `Change: ${data.comparison.change}` : undefined} />
      <p className="mb-4 text-sm">
        <Link href={`/runs/${id}`} className="underline decoration-transparent underline-offset-2 hover:decoration-[var(--ink)]">
          Back to run
        </Link>
      </p>
      <section className="mb-4 panel p-3">
        <h2 className="text-xs uppercase tracking-wide text-[var(--muted)]">Input</h2>
        <p className="mt-1">{input}</p>
        <h2 className="mt-3 text-xs uppercase tracking-wide text-[var(--muted)]">Expected</h2>
        <p className="num mt-1 text-xs">
          outcome {expected?.expected_outcome || "n/a"} · must call {(expected?.must_call || []).join(", ") || "none"} ·
          must not call {(expected?.must_not_call || []).join(", ") || "none"}
        </p>
        {expected?.expected_output ? <p className="mt-1 text-sm">Exact output: {expected.expected_output}</p> : null}
      </section>
      <div className="grid gap-3 md:grid-cols-2">
        <SideCard title="Baseline" side={data.baseline} />
        <SideCard title="Candidate" side={data.candidate} />
      </div>
    </div>
  );
}

function SideCard({ title, side }: { title: string; side: Side | null }) {
  if (!side) return <section className="panel p-3 text-sm">No {title.toLowerCase()} result.</section>;
  return (
    <section className="panel p-3 text-sm">
      <h2 className="text-xs uppercase tracking-wide text-[var(--muted)]">{title}</h2>
      <p className="mt-1 font-medium">
        {side.status}
        {side.failure_class ? ` · ${side.failure_class}` : ""}
      </p>
      {side.error ? <p className="mt-2 text-[#f3b0aa]">{side.error}</p> : null}
      <p className="mt-2">Outcome: <span className="num">{side.outcome || "n/a"}</span></p>
      <p className="mt-1 whitespace-pre-wrap">{side.output || "No output"}</p>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div>Request {formatMs(side.latency_ms)}</div>
        <div>Model {formatMs(side.model_latency_ms)}</div>
        <div>Tools {formatMs(side.tool_latency_ms)}</div>
        <div>Evaluators {formatMs(side.evaluation_latency_ms)}</div>
        <div className="col-span-2">Cost {side.cost_status === "measured" ? formatUsd(side.cost_usd) : "Not measured"}</div>
      </dl>
      <h3 className="mt-3 text-xs uppercase tracking-wide text-[var(--muted)]">Tool calls</h3>
      {side.tool_calls.length === 0 ? (
        <p className="text-xs text-[var(--muted)]">None</p>
      ) : (
        <ul className="mt-1 space-y-2">
          {side.tool_calls.map((call, index) => (
            <li key={`${call.name}-${index}`} className="rounded-lg bg-[var(--hover)] px-2 py-1 text-xs">
              <span className="num">{call.name}</span> {formatMs(call.latency_ms)}
              {call.error ? <span className="text-[#f3b0aa]"> {call.error}</span> : null}
              <pre className="mt-1 overflow-auto">{JSON.stringify(call.arguments)}</pre>
            </li>
          ))}
        </ul>
      )}
      <h3 className="mt-3 text-xs uppercase tracking-wide text-[var(--muted)]">Evaluators</h3>
      <ul className="mt-1 space-y-2">
        {side.evaluator_results.map((item) => (
          <li key={item.evaluator} className="text-xs">
            <span className="font-medium">{item.evaluator}</span>{" "}
            <span className="uppercase text-[var(--muted)]">{item.kind}</span> · {item.status}
            <div>{item.detail}</div>
          </li>
        ))}
      </ul>
    </section>
  );
}
