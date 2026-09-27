"use server";

import { redirect } from "next/navigation";
import { API_URL } from "@/lib/api";

export async function runEvaluation(formData: FormData) {
  const projectId = String(formData.get("projectId") || "");
  const candidate = String(formData.get("candidate") || "");
  const baseline = String(formData.get("baseline") || "");
  const trials = Number(formData.get("trials") || 1);
  const response = await fetch(`${API_URL}/api/v1/projects/${projectId}/evaluate`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      candidate: candidate || null,
      baseline: baseline || null,
      trials,
    }),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(typeof body.detail === "string" ? body.detail : "Evaluation failed");
  }
  redirect(`/runs/${body.run_id}`);
}

export async function replayRun(formData: FormData) {
  const runId = String(formData.get("runId") || "");
  const response = await fetch(`${API_URL}/api/v1/runs/${runId}/replay`, { method: "POST" });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(typeof body.detail === "string" ? body.detail : "Replay failed");
  }
  redirect(`/runs/${body.run_id}`);
}
