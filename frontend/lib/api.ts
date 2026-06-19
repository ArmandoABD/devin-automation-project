// Typed client for the orchestrator API.

export type Vertical = "security" | "backlog" | "both";
export type SessionStatus =
  | "pending"
  | "working"
  | "blocked"
  | "finished"
  | "failed"
  | "expired";

export interface RemediationSession {
  finding_id: string;
  finding_title: string;
  vertical: Vertical;
  session_id?: string | null;
  session_url?: string | null;
  status: SessionStatus;
  pr_url?: string | null;
  tests_pass?: boolean | null;
  summary: string;
}

export interface Finding {
  id: string;
  vertical: Vertical;
  severity: string;
  title: string;
  target: string;
  issue_url?: string | null;
}

export interface ScanSnapshot {
  npm_vulns?: number | null;
  py_vulns?: number | null;
  any_types?: number | null;
}

export interface Run {
  id: string;
  vertical: Vertical;
  phase: "discovering" | "remediating" | "completed" | "failed" | "stopped";
  created_at: string;
  updated_at: string;
  discovery_session_url?: string | null;
  findings: Finding[];
  sessions: RemediationSession[];
  before?: ScanSnapshot | null;
  after?: ScanSnapshot | null;
  error?: string | null;
}

export interface Metrics {
  total_runs: number;
  findings_discovered: number;
  sessions_started: number;
  prs_opened: number;
  succeeded: number;
  failed: number;
  in_progress: number;
  success_rate: number;
  vulns_remediated: number;
}

export interface Health {
  status: string;
  demo_mode: boolean;
  devin_base_url: string;
  github_repo: string;
  repo_scanning: boolean;
}

const BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export const api = {
  health: () => j<Health>("/api/health"),
  metrics: () => j<Metrics>("/api/metrics"),
  listRuns: () => j<Run[]>("/api/runs"),
  getRun: (id: string) => j<Run>(`/api/runs/${id}`),
  triggerRun: (vertical: Vertical) =>
    j<Run>("/api/runs", {
      method: "POST",
      body: JSON.stringify({ vertical }),
    }),
  verifyImpact: (id: string) =>
    j<Run>(`/api/runs/${id}/verify`, { method: "POST" }),
  stopRun: (id: string) => j<Run>(`/api/runs/${id}/stop`, { method: "POST" }),
};
