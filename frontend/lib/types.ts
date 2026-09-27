export type Nullable<T> = T | null;

export type Metrics = {
  total_cases: number;
  completed_cases: number;
  passed_cases: number;
  failed_cases: number;
  infrastructure_errors: number;
  provider_errors: number;
  accuracy: Nullable<number>;
  median_latency_ms: Nullable<number>;
  p95_latency_ms: Nullable<number>;
  average_cost_usd: Nullable<number>;
  cost_status: "measured" | "partial" | "unavailable";
  tool_success_rate: Nullable<number>;
  human_review_rate: Nullable<number>;
};

export type Version = {
  name: string;
  version: string;
  commit: Nullable<string>;
  provider: string;
  provider_class: "deterministic_harness" | "model" | "development_double";
  model: Nullable<string>;
  config_hash: string;
  harness_path: Nullable<string>;
  execution_mode: "policy" | "llm";
};

export type Rule = {
  metric: string;
  label: string;
  status: "pass" | "review" | "block" | "skipped" | "not_measured";
  baseline: Nullable<number>;
  candidate: Nullable<number>;
  delta: Nullable<number>;
  delta_percent: Nullable<number>;
  delta_kind: "points" | "relative" | "absolute" | "none";
  unit: "ratio" | "milliseconds" | "usd" | "count";
  detail: string;
};

export type Variance = {
  trials: number;
  min_trials: number;
  sufficient: boolean;
  mean_accuracy: Nullable<number>;
  median_accuracy: Nullable<number>;
  sample_variance: Nullable<number>;
  note: string;
};

export type RunSummary = {
  id: string;
  project_id: string;
  decision: "pass" | "review" | "block";
  inconclusive: boolean;
  started_at: string;
  completed_at: Nullable<string>;
  baseline: Nullable<Version>;
  candidate: Version;
  baseline_metrics: Nullable<Metrics>;
  candidate_metrics: Metrics;
  variance: Variance;
  reasons: string[];
};

export type Overview = {
  projects: number;
  runs: number;
  decisions: { pass: number; review: number; block: number };
  mean_candidate_accuracy: Nullable<number>;
  mean_candidate_median_latency_ms: Nullable<number>;
  mean_candidate_cost_usd: Nullable<number>;
  cost_runs_measured: number;
  recent_runs: RunSummary[];
  regressions: RunSummary[];
};
