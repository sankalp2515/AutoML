import type {
  Run,
  RunDetail,
  Artifact,
  LLMStat,
  AgentTimingEntry,
  Results,
  FeatureSchema,
  DeploymentInfo,
  Prediction,
  PredictionLogEntry,
  DriftReport,
  Notebook,
} from './types';

import { getAccessToken } from './supabase';

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const WS_BASE = API_BASE.replace('http://', 'ws://').replace(
  'https://',
  'wss://'
);

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  // Attach the Supabase access token when signed in (no-op if auth disabled).
  const token = await getAccessToken();
  const headers = new Headers(init?.headers);
  headers.set('Accept', 'application/json');
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {}
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

// ── Runs ──────────────────────────────────────────────────────────────────────

export async function createRun(formData: FormData): Promise<Run> {
  return apiRequest<Run>('/api/v1/runs', { method: 'POST', body: formData });
}

export async function listRuns(skip = 0, limit = 30): Promise<{ runs: Run[]; total: number }> {
  return apiRequest<{ runs: Run[]; total: number }>(
    `/api/v1/runs?skip=${skip}&limit=${limit}`
  );
}

export async function getRun(runId: string): Promise<RunDetail> {
  return apiRequest<RunDetail>(`/api/v1/runs/${runId}`);
}

export async function getResults(runId: string): Promise<Results> {
  return apiRequest<Results>(`/api/v1/runs/${runId}/results`);
}

// ── Artifacts ─────────────────────────────────────────────────────────────────

export async function listArtifacts(runId: string): Promise<Artifact[]> {
  const data = await apiRequest<{ artifacts: Artifact[] }>(
    `/api/v1/runs/${runId}/artifacts`
  );
  return data.artifacts;
}

export function artifactUrl(runId: string, name: string): string {
  return `${API_BASE}/api/v1/runs/${runId}/artifacts/${name}`;
}

export async function fetchArtifactText(runId: string, name: string): Promise<string> {
  const res = await fetch(artifactUrl(runId, name));
  if (!res.ok) throw new Error(`Artifact fetch failed: ${res.status}`);
  return res.text();
}

// ── Observability ─────────────────────────────────────────────────────────────

// Backend response shape for /llm-stats
interface LLMStatsApiResponse {
  run_id: string;
  per_agent: {
    agent: string;
    calls: number;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    avg_latency_ms: number;
    max_latency_ms: number;
    estimated_cost_usd: number;
  }[];
  totals: {
    total_calls: number;
    total_tokens: number;
    total_cost_usd: number;
    avg_latency_ms: number;
  };
}

export async function getLLMStats(runId: string): Promise<{ stats: LLMStat[]; totals: LLMStat }> {
  const data = await apiRequest<LLMStatsApiResponse>(
    `/api/v1/runs/${runId}/llm-stats`
  );
  const stats: LLMStat[] = data.per_agent.map((a) => ({
    agent_name: a.agent,
    n_calls: a.calls,
    total_prompt_tokens: a.prompt_tokens,
    total_completion_tokens: a.completion_tokens,
    total_tokens: a.total_tokens,
    total_cost_usd: a.estimated_cost_usd,
    avg_latency_ms: a.avg_latency_ms,
  }));
  const totals: LLMStat = {
    agent_name: 'total',
    n_calls: data.totals.total_calls,
    total_prompt_tokens: stats.reduce((s, a) => s + a.total_prompt_tokens, 0),
    total_completion_tokens: stats.reduce((s, a) => s + a.total_completion_tokens, 0),
    total_tokens: data.totals.total_tokens,
    total_cost_usd: data.totals.total_cost_usd,
    avg_latency_ms: data.totals.avg_latency_ms,
  };
  return { stats, totals };
}

export async function getAgentTimeline(runId: string): Promise<{ timeline: AgentTimingEntry[] }> {
  return apiRequest<{ timeline: AgentTimingEntry[] }>(
    `/api/v1/runs/${runId}/agent-timeline`
  );
}

// ── Phase 3: inference & drift ────────────────────────────────────────────────

export async function deployModel(runId: string): Promise<{ deployment_id: string; status: string }> {
  return apiRequest(`/api/v1/runs/${runId}/deploy`, { method: 'POST' });
}

export async function stopDeployment(runId: string): Promise<{ status: string }> {
  return apiRequest(`/api/v1/runs/${runId}/deploy`, { method: 'DELETE' });
}

export async function listDeployments(): Promise<{ deployments: DeploymentInfo[] }> {
  return apiRequest('/api/v1/deployments');
}

export async function getFeatureSchema(
  runId: string
): Promise<{ features: FeatureSchema[]; target_column: string | null; task_type: string | null }> {
  return apiRequest(`/api/v1/runs/${runId}/schema`);
}

export async function predictRows(
  runId: string,
  rows: Record<string, unknown>[]
): Promise<{ predictions: Prediction[]; model: string; latency_ms: number }> {
  return apiRequest(`/api/v1/runs/${runId}/predict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rows }),
  });
}

export async function getPredictionLog(
  runId: string,
  limit = 50
): Promise<{ predictions: PredictionLogEntry[] }> {
  return apiRequest(`/api/v1/runs/${runId}/predictions?limit=${limit}`);
}

export async function getDriftReport(runId: string): Promise<DriftReport> {
  return apiRequest(`/api/v1/runs/${runId}/drift`);
}

// ── Notebook ──────────────────────────────────────────────────────────────────

export async function fetchNotebook(runId: string): Promise<Notebook> {
  const text = await fetchArtifactText(runId, 'notebook');
  return JSON.parse(text) as Notebook;
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

export function connectWebSocket(
  runId: string,
  onMessage: (msg: Record<string, unknown>) => void,
  onClose?: () => void
): WebSocket {
  // Must match the backend route: /ws/runs/{run_id}/progress
  const url = `${WS_BASE}/ws/runs/${runId}/progress`;
  const ws = new WebSocket(url);

  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data as string) as Record<string, unknown>;
      onMessage(msg);
    } catch {}
  };

  ws.onerror = () => {
    ws.close();
  };

  if (onClose) {
    ws.onclose = onClose;
  }

  return ws;
}

// ── Backlog P10–P15 client functions ──────────────────────────────────────────
export async function compareRuns(a: string, b: string) {
  return apiRequest<Record<string, unknown>>(`/api/v1/runs/compare?a=${a}&b=${b}`);
}

export async function askModel(runId: string, question: string) {
  return apiRequest<{ answer: string; cited_agents?: string[] }>(
    `/api/v1/runs/${runId}/ask`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }) }
  );
}

export async function explainPrediction(runId: string, rows: Record<string, unknown>[]) {
  return apiRequest<{ explanations: { feature: string; contribution: number }[][] }>(
    `/api/v1/runs/${runId}/explain`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rows }) }
  );
}

export async function fairnessAudit(runId: string, columns: string) {
  return apiRequest<Record<string, unknown>>(
    `/api/v1/runs/${runId}/fairness?columns=${encodeURIComponent(columns)}`
  );
}

export async function retrainChallenger(runId: string) {
  return apiRequest<{ champion_run_id: string; challenger_run_id: string; note: string }>(
    `/api/v1/runs/${runId}/retrain`, { method: 'POST' }
  );
}

export function batchPredictUrl(runId: string): string {
  return `${API_BASE}/api/v1/runs/${runId}/batch-predict`;
}
