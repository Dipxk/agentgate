import { runEvaluation } from "@/app/actions";
import { ApiDown, PageHeader } from "@/components/PageHeader";
import { RunTable } from "@/components/RunTable";
import { apiGet } from "@/lib/api";
import type { RunSummary } from "@/lib/types";

type Version = { name: string; path: string; role: string };
type ProjectDetail = {
  id: string;
  name: string;
  description: string;
  config: {
    dataset?: string;
    gates?: string;
    pricing?: string;
    versions?: Version[];
  };
  gates: Record<string, unknown> | null;
  runs: RunSummary[];
};

export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { data, error } = await apiGet<ProjectDetail>(`/api/v1/projects/${id}`);
  if (error || !data) return <ApiDown message={error || "Project not found"} />;
  const versions = data.config.versions || [];
  const production = versions.find((item) => item.role === "production");

  return (
    <div>
      <PageHeader title={data.name} detail={data.description} />
      <dl className="mb-6 grid gap-3 md:grid-cols-3">
        <Fact label="Dataset" value={data.config.dataset || "Not configured"} />
        <Fact label="Gates" value={data.config.gates || "Not configured"} />
        <Fact label="Pricing" value={data.config.pricing || "Not configured"} />
      </dl>

      <h2 className="mb-2 text-sm font-semibold">Harness versions</h2>
      {versions.length === 0 ? (
        <p className="mb-6 text-sm text-[var(--muted)]">No versions recorded on this project.</p>
      ) : (
        <div className="mb-6 overflow-hidden panel">
          <table className="text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-[var(--muted)]">
              <tr>
                <th className="px-3 py-2 font-medium">Name</th>
                <th className="px-3 py-2 font-medium">Role</th>
                <th className="px-3 py-2 font-medium">Path</th>
              </tr>
            </thead>
            <tbody>
              {versions.map((version) => (
                <tr key={version.path} className="border-t border-[var(--line)]">
                  <td className="px-3 py-2">{version.name}</td>
                  <td className="px-3 py-2">{version.role}</td>
                  <td className="num px-3 py-2 text-xs">{version.path}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2 className="mb-2 text-sm font-semibold">Release gates</h2>
      <GateTable gates={data.gates} />

      <h2 className="mb-2 mt-8 text-sm font-semibold">Run an evaluation</h2>
      <form action={runEvaluation} className="mb-8 grid gap-3 panel p-4 md:grid-cols-4">
        <input type="hidden" name="projectId" value={data.id} />
        <label className="text-xs text-[var(--muted)]">
          Baseline path
          <input
            name="baseline"
            defaultValue={production?.path || "evaluation/agents/baseline.yaml"}
            className="mt-1 w-full rounded border border-[var(--line)] px-2 py-1.5 text-sm text-[var(--ink)]"
          />
        </label>
        <label className="text-xs text-[var(--muted)]">
          Candidate path
          <select name="candidate" className="mt-1 w-full rounded border border-[var(--line)] px-2 py-1.5 text-sm text-[var(--ink)]">
            {versions.filter((item) => item.role !== "production").map((version) => (
              <option key={version.path} value={version.path}>
                {version.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-[var(--muted)]">
          Trials
          <input
            name="trials"
            type="number"
            min={1}
            max={20}
            defaultValue={1}
            className="mt-1 w-full rounded border border-[var(--line)] px-2 py-1.5 text-sm text-[var(--ink)]"
          />
        </label>
        <div className="flex items-end">
          <button type="submit" className="rounded-lg bg-[var(--ink)] px-3 py-1.5 text-sm text-[var(--bg)] hover:opacity-90">
            Evaluate
          </button>
        </div>
      </form>

      <h2 className="mb-2 text-sm font-semibold">Stored runs</h2>
      <RunTable runs={data.runs} />
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel px-3 py-3">
      <dt className="text-xs uppercase tracking-wide text-[var(--muted)]">{label}</dt>
      <dd className="num mt-1 text-xs">{value}</dd>
    </div>
  );
}

function GateTable({ gates }: { gates: Record<string, unknown> | null }) {
  if (!gates) return <p className="text-sm text-[var(--muted)]">Gate file could not be loaded.</p>;
  const rows = Object.entries(gates).filter(([, value]) => value && typeof value === "object");
  return (
    <div className="overflow-hidden panel">
      <table className="text-sm">
        <thead className="text-left text-xs uppercase tracking-wide text-[var(--muted)]">
          <tr>
            <th className="px-3 py-2 font-medium">Rule</th>
            <th className="px-3 py-2 font-medium">Configuration</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, value]) => (
            <tr key={name} className="border-t border-[var(--line)] align-top">
              <td className="px-3 py-2">{name}</td>
              <td className="num px-3 py-2 text-xs">{JSON.stringify(value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
