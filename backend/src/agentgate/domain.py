"""Shared data model for datasets, runs, and gate decisions."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LLMJudgeCriteria(BaseModel):
    """Subjective rubric. Never sufficient to pass or block a release."""

    model_config = ConfigDict(extra="forbid")

    rubric: str = Field(min_length=1)


class DeterministicTest(BaseModel):
    """A trusted test supplied by the dataset, never by model output."""

    model_config = ConfigDict(extra="forbid")

    language: Literal["python"] = "python"
    source: str = Field(min_length=1)


class ExpectedBehavior(BaseModel):
    model_config = ConfigDict(extra="forbid")

    must_call: List[str] = Field(default_factory=list)
    must_not_call: List[str] = Field(default_factory=list)
    call_order: List[str] = Field(default_factory=list)
    expected_outcome: Optional[str] = None
    expected_output: Optional[str] = None
    latency_threshold_ms: Optional[float] = None
    cost_threshold_usd: Optional[float] = None
    deterministic_test: Optional[DeterministicTest] = None
    llm_judge: Optional[LLMJudgeCriteria] = None

    @field_validator("latency_threshold_ms", "cost_threshold_usd")
    @classmethod
    def _non_negative(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and value < 0:
            raise ValueError("thresholds must be >= 0")
        return value


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    input: str
    expected_behavior: ExpectedBehavior
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    description: str
    cases: List[EvalCase]

    @field_validator("cases")
    @classmethod
    def _unique_ids(cls, cases: List[EvalCase]) -> List[EvalCase]:
        ids = [case.id for case in cases]
        if len(ids) != len(set(ids)):
            raise ValueError("evaluation case ids must be unique")
        if not cases:
            raise ValueError("dataset must contain at least one case")
        return cases


class ToolCall(BaseModel):
    name: str
    arguments: Dict[str, Any]
    result: Optional[Any] = None
    latency_ms: float
    error: Optional[str] = None


class AgentResponse(BaseModel):
    """What the runner observed. Cost is not trusted from the agent."""

    output: str
    outcome: Optional[str] = None
    tool_calls: List[ToolCall] = Field(default_factory=list)
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    model_latency_ms: Optional[float] = None
    needs_human_review: Optional[bool] = None
    provider: str
    provider_class: Literal["deterministic_harness", "model", "development_double"]
    model: Optional[str] = None
    error: Optional[str] = None

    @field_validator("input_tokens", "output_tokens")
    @classmethod
    def _tokens(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value < 0:
            raise ValueError("token counts must be >= 0")
        return value


class EvaluatorResult(BaseModel):
    evaluator: str
    kind: Literal["deterministic", "subjective"]
    status: Literal["pass", "fail", "skip", "infrastructure_error", "provider_error", "not_run"]
    detail: str


class CaseResult(BaseModel):
    case_id: str
    case_input: Optional[str] = None
    expected_outcome: Optional[str] = None
    expected_output: Optional[str] = None
    must_call: List[str] = Field(default_factory=list)
    must_not_call: List[str] = Field(default_factory=list)
    side: Literal["baseline", "candidate"]
    trial: int
    status: Literal["passed", "failed", "infrastructure_error", "provider_error"]
    failure_class: Optional[Literal["agent", "infrastructure", "provider"]] = None
    output: Optional[str] = None
    outcome: Optional[str] = None
    tool_calls: List[ToolCall] = Field(default_factory=list)
    evaluator_results: List[EvaluatorResult] = Field(default_factory=list)
    latency_ms: Optional[float] = None
    model_latency_ms: Optional[float] = None
    tool_latency_ms: Optional[float] = None
    evaluation_latency_ms: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    cost_status: Literal["measured", "unavailable"] = "unavailable"
    needs_human_review: Optional[bool] = None
    error: Optional[str] = None


class VersionRef(BaseModel):
    name: str
    version: str
    commit: Optional[str] = None
    provider: str
    provider_class: Literal["deterministic_harness", "model", "development_double"]
    model: Optional[str] = None
    config_hash: str
    harness_path: Optional[str] = None
    execution_mode: Literal["policy", "llm"]


class RunMetrics(BaseModel):
    total_cases: int
    completed_cases: int
    passed_cases: int
    failed_cases: int
    infrastructure_errors: int
    provider_errors: int
    accuracy: Optional[float] = None
    median_latency_ms: Optional[float] = None
    p95_latency_ms: Optional[float] = None
    average_cost_usd: Optional[float] = None
    cost_status: Literal["measured", "partial", "unavailable"] = "unavailable"
    tool_success_rate: Optional[float] = None
    human_review_rate: Optional[float] = None


class RuleResult(BaseModel):
    metric: str
    label: str
    status: Literal["pass", "review", "block", "skipped", "not_measured"]
    baseline: Optional[float] = None
    candidate: Optional[float] = None
    delta: Optional[float] = None
    delta_percent: Optional[float] = None
    delta_kind: Literal["points", "relative", "absolute", "none"] = "none"
    unit: Literal["ratio", "milliseconds", "usd", "count"] = "ratio"
    detail: str


class GateOutcome(BaseModel):
    decision: Literal["pass", "review", "block"]
    inconclusive: bool = False
    reasons: List[str]
    rules: List[RuleResult]
    subjective_failures: int = 0
    development_provider: bool = False


class VarianceReport(BaseModel):
    trials: int
    min_trials: int
    sufficient: bool
    mean_accuracy: Optional[float] = None
    median_accuracy: Optional[float] = None
    sample_variance: Optional[float] = None
    note: str


class CaseComparison(BaseModel):
    case_id: str
    baseline_status: Optional[str] = None
    candidate_status: Optional[str] = None
    baseline_outcome: Optional[str] = None
    candidate_outcome: Optional[str] = None
    change: Literal["regression", "fix", "unchanged", "unscored"]


class RunManifest(BaseModel):
    run_id: str
    project: str
    dataset_name: str
    dataset_version: str
    dataset_hash: str
    dataset_path: Optional[str] = None
    evaluator_version: str
    agentgate_version: str
    seed: Optional[int] = None
    trials: int
    environment: Dict[str, Any]
    baseline: Optional[VersionRef] = None
    candidate: VersionRef
    started_at: str
    completed_at: Optional[str] = None
    status: Literal["running", "completed", "failed"] = "running"


class EvaluationReport(BaseModel):
    manifest: RunManifest
    baseline_metrics: Optional[RunMetrics] = None
    candidate_metrics: RunMetrics
    gate: GateOutcome
    variance: VarianceReport
    case_results: List[CaseResult]
    comparisons: List[CaseComparison]
    logs: List[Dict[str, Any]]
    text: str
