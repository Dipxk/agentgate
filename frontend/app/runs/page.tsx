import { ApiDown, PageHeader } from "@/components/PageHeader";
import { RunTable } from "@/components/RunTable";
import { apiGet } from "@/lib/api";
import type { RunSummary } from "@/lib/types";

export default async function RunsPage() {
  const { data, error } = await apiGet<RunSummary[]>("/api/v1/runs");
  if (error || !data) return <ApiDown message={error || "No data"} />;
  return (
    <div>
      <PageHeader title="Runs" detail="Every row is a stored evaluation. Open a run to see the case-level diff." />
      <RunTable runs={data} />
    </div>
  );
}
