export const API_URL = process.env.AGENTGATE_API_URL || "http://127.0.0.1:8000";

export async function apiGet<T>(path: string): Promise<{ data: T | null; error: string | null }> {
  try {
    const response = await fetch(`${API_URL}${path}`, { cache: "no-store" });
    if (!response.ok) {
      const body = await response.text();
      return { data: null, error: body || `HTTP ${response.status}` };
    }
    return { data: (await response.json()) as T, error: null };
  } catch (error) {
    return {
      data: null,
      error: `The AgentGate API is not reachable at ${API_URL}. Start it with \`agentgate serve\`. ${String(error)}`,
    };
  }
}
