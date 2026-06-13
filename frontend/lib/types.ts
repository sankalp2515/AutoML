export type RunStatus = 'queued' | 'running' | 'completed' | 'failed';

export interface AgentStep {
  agent_name: string;
  status: 'running' | 'completed' | 'failed';
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
}

export interface DecisionLog {
  agent_name: string;
  timestamp: string;
  decision: string;
  reasoning: string;
  code_executed: string;
  result_summary: string;
}

export interface Run {
  id: string;
  status: RunStatus;
  dataset_filename: string;
  user_goal: string;
  task_type: string | null;
  target_column: string | null;
  primary_metric: string | null;
  baseline_score: number | null;
  final_score: number | null;
  winner_model: string | null;
  iteration_count: number | null;
  error_message: string | null;
  mlflow_run_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface RunDetail extends Run {
  agent_steps: AgentStep[];
  decision_logs: DecisionLog[];
}

export interface Artifact {
  name: string;
  filename: string;
  size_kb: number;
  download_url: string;
}

export interface ProgressMessage {
  agent: string;
  message: string;
  timestamp: string;
  data?: Record<string, unknown>;
}

export interface LLMStat {
  agent_name: string;
  n_calls: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
  avg_latency_ms: number;
}

export interface AgentTimingEntry {
  agent_name: string;
  started_at: string | null;
  completed_at: string | null;
  duration_s: number | null;
  status: string;
}

export interface EvalReport {
  metrics: Record<string, number>;
  calibration: {
    mean_calibration_error: number;
    well_calibrated: boolean;
  } | null;
}

// ── Phase 3: inference & drift ────────────────────────────────────────────────

export interface FeatureSchema {
  name: string;
  type: 'number' | 'text';
  example: string;
}

export interface DeploymentInfo {
  deployment_id: string;
  run_id: string;
  status: 'active' | 'stopped';
  model: string | null;
  n_predictions: number;
  deployed_at: string | null;
}

export interface Prediction {
  prediction: string;
  confidence: number | null;
}

export interface PredictionLogEntry {
  id: string;
  features: Record<string, unknown>;
  prediction: string;
  confidence: number | null;
  latency_ms: number;
  created_at: string | null;
}

export interface DriftFeature {
  feature: string;
  psi: number | null;
  ks_pvalue: number | null;
  status: 'stable' | 'moderate' | 'drifted' | 'unknown';
}

export interface DriftReport {
  run_id: string;
  status: 'ok' | 'insufficient_data';
  message?: string;
  n_predictions?: number;
  features?: DriftFeature[];
  max_psi?: number;
  n_features_checked?: number;
  n_drifted?: number;
  n_samples_current?: number;
  n_samples_reference?: number;
  overall_status?: 'stable' | 'moderate' | 'drifted';
}

// ── Notebook (.ipynb) ─────────────────────────────────────────────────────────

export interface NotebookCell {
  cell_type: 'markdown' | 'code';
  source: string | string[];
  outputs?: unknown[];
}

export interface Notebook {
  cells: NotebookCell[];
}

export interface Results {
  run_id: string;
  task_type: string | null;
  target_column: string | null;
  primary_metric: string | null;
  baseline_score: number | null;
  final_score: number | null;
  winner_model: string | null;
  iteration_count: number | null;
  evaluation_report: EvalReport | null;
  shap_top_features: string[] | null;
  artifact_paths: Record<string, string> | null;
}
