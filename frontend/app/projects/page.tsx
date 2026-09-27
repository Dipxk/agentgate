import Link from "next/link";
import { ApiDown, PageHeader } from "@/components/PageHeader";
import { apiGet } from "@/lib/api";

type Project = { id: string; name: string; description: string; created_at: string };

export default async function ProjectsPage() {
  const { data, error } = await apiGet<Project[]>("/api/v1/projects");
  if (error || !data) return <ApiDown message={error || "No data"} />;
  return (
    <div>
      <PageHeader title="Projects" detail="Each project pins a dataset, a gate file, and the harness versions under evaluation." />
      {data.length === 0 ? (
        <p className="text-sm text-[var(--muted)]">No projects yet. Run `agentgate demo` to store the demonstration project.</p>
      ) : (
        <ul className="panel divide-y divide-[var(--line)] overflow-hidden">
          {data.map((project) => (
            <li key={project.id}>
              <Link href={`/projects/${project.id}`} className="block px-4 py-3 hover:bg-[var(--hover)]">
                <div className="font-medium">{project.name}</div>
                <p className="mt-1 text-sm text-[var(--muted)]">{project.description}</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
