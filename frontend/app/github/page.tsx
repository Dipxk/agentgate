import Link from "next/link";
import { ApiDown, PageHeader } from "@/components/PageHeader";
import { apiGet } from "@/lib/api";
import type { RunSummary } from "@/lib/types";

type Delivery = {
  id: string;
  run_id: string | null;
  repository: string | null;
  pull_request: number | null;
  delivered: boolean;
  created_at: string;
  comment_body: string;
};

export default async function GithubPage({
  searchParams,
}: {
  searchParams: Promise<{ run?: string }>;
}) {
  const query = await searchParams;
  const github = await apiGet<{ token_configured: boolean; deliveries: Delivery[] }>("/api/v1/github");
  const runs = await apiGet<RunSummary[]>("/api/v1/runs");
  if (github.error || !github.data) return <ApiDown message={github.error || "GitHub status unavailable"} />;

  let preview: string | null = null;
  let previewError: string | null = null;
  if (query.run) {
    const comment = await apiGet<{ body: string }>(`/api/v1/runs/${query.run}/comment`);
    preview = comment.data?.body || null;
    previewError = comment.error;
  }

  return (
    <div>
      <PageHeader
        title="GitHub"
        detail="Pull request comments are rendered from a measured run. A preview on this page is not a delivery."
      />
      <dl className="mb-6 grid gap-3 md:grid-cols-2">
        <div className="panel px-3 py-3">
          <dt className="text-xs uppercase tracking-wide text-[var(--muted)]">Token</dt>
          <dd className="mt-1">{github.data.token_configured ? "Configured in the API environment" : "Not configured"}</dd>
        </div>
        <div className="panel px-3 py-3">
          <dt className="text-xs uppercase tracking-wide text-[var(--muted)]">Workflow</dt>
          <dd className="mt-1 text-sm">`.github/workflows/agentgate.yml` runs the same engine as this API.</dd>
        </div>
      </dl>

      <h2 className="mb-2 text-sm font-semibold">Comment preview</h2>
      <p className="mb-2 text-xs text-[var(--muted)]">Choose a stored run. This does not post to GitHub.</p>
      <ul className="mb-4 flex flex-wrap gap-2">
        {(runs.data || []).map((run) => (
          <li key={run.id}>
            <Link href={`/github?run=${run.id}`} className="num inline-block rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1 text-xs hover:bg-[var(--hover)]">
              {run.candidate.name} · {run.decision} · {run.id.slice(0, 8)}
            </Link>
          </li>
        ))}
      </ul>
      {previewError ? <p className="text-sm text-[#f3b0aa]">{previewError}</p> : null}
      {preview ? (
        <pre className="mb-8 overflow-auto panel p-3 text-xs leading-5">{preview}</pre>
      ) : (
        <p className="mb-8 text-sm text-[var(--muted)]">No preview selected.</p>
      )}

      <h2 className="mb-2 text-sm font-semibold">Deliveries</h2>
      {github.data.deliveries.length === 0 ? (
        <p className="text-sm text-[var(--muted)]">No GitHub delivery has been recorded. The Action posts one when it runs with GITHUB_TOKEN.</p>
      ) : (
        <ul className="space-y-3">
          {github.data.deliveries.map((delivery) => (
            <li key={delivery.id} className="panel p-3 text-sm">
              <div>
                {delivery.delivered ? "Posted" : "Stored, not posted"}
                {delivery.repository ? ` · ${delivery.repository}` : ""}
                {delivery.pull_request ? ` #${delivery.pull_request}` : ""}
              </div>
              <pre className="mt-2 overflow-auto text-xs">{delivery.comment_body}</pre>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
