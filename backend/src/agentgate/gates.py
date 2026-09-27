"""Transparent release-gate rules.

A critical miss blocks. A review-severity miss asks for a human. Subjective
LLM-judge failures can only move a decision toward review. A development
double (MockProvider) cannot pass a gate.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentgate.domain import GateOutcome, RuleResult, RunMetrics
from agentgate.variance import VarianceReport

Severity = Literal["critical", "review"]
Missing = Literal["skip", "review", "block"]


class MetricRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum: Optional[float] = None
    maximum: Optional[float] = None
    max_regression: Optional[float] = None
    max_increase: Optional[float] = None
    max_decrease: Optional[float] = None
    max_increase_percent: Optional[float] = None
    min_baseline_for_percent: Optional[float] = None
    severity: Severity = "critical"
    on_missing: Missing = "skip"

    @model_validator(mode="after")
    def _sane(self) -> "MetricRule":
        for name in (
            "minimum",
            "maximum",
            "max_regression",
            "max_increase",
            "max_decrease",
            "max_increase_percent",
            "min_baseline_for_percent",
        ):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be >= 0")
        return self


class GateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accuracy: MetricRule = Field(default_factory=MetricRule)
    tool_success: MetricRule = Field(default_factory=MetricRule)
    latency_p95_ms: MetricRule = Field(
        default_factory=lambda: MetricRule(severity="review", on_missing="skip")
    )
    latency_median_ms: MetricRule = Field(
        default_factory=lambda: MetricRule(severity="review", on_missing="skip")
    )
    cost_per_request_usd: MetricRule = Field(
        default_factory=lambda: MetricRule(severity="review", on_missing="skip")
    )
    human_review_rate: MetricRule = Field(
        default_factory=lambda: MetricRule(severity="review", on_missing="skip")
    )
    min_trials: int = Field(default=5, ge=1)
    review_on_insufficient_trials: bool = False


def _status_for(severity: Severity) -> Literal["review", "block"]:
    return "block" if severity == "critical" else "review"


def _missing(rule: MetricRule, detail: str) -> RuleResult:
    status: Literal["pass", "review", "block", "skipped", "not_measured"]
    if rule.on_missing == "skip":
        status = "not_measured"
    else:
        status = _status_for("critical" if rule.on_missing == "block" else "review")
    return RuleResult(metric="", label="", status=status, detail=detail)


def _relative_change(baseline: float, candidate: float) -> Optional[float]:
    if baseline == 0:
        return None
    return (candidate - baseline) / baseline * 100.0


def _worse(current: str, proposed: str) -> str:
    rank = {"pass": 0, "skipped": 0, "not_measured": 0, "review": 1, "block": 2}
    return proposed if rank[proposed] > rank[current] else current


def _higher_is_better(
    rule: MetricRule,
    baseline: Optional[float],
    candidate: Optional[float],
    label: str,
    metric: str,
) -> RuleResult:
    if candidate is None:
        result = _missing(rule, f"{label} was not measured. It was not scored as 0.")
        result.metric = metric
        result.label = label
        result.unit = "ratio"
        result.delta_kind = "points"
        return result

    status = "pass"
    details: List[str] = []
    delta = None if baseline is None else candidate - baseline
    if rule.minimum is not None and candidate < rule.minimum:
        status = _worse(status, _status_for(rule.severity))
        details.append(f"{label} {candidate:.4f} is below minimum {rule.minimum:.4f}.")
    if baseline is not None and rule.max_regression is not None:
        drop = baseline - candidate
        if drop > rule.max_regression:
            status = _worse(status, _status_for(rule.severity))
            details.append(
                f"{label} fell by {drop:.4f}, above the allowed regression of {rule.max_regression:.4f}."
            )
    if not details:
        if delta is None:
            details.append(f"{label} meets the absolute threshold. No baseline was supplied.")
        elif delta > 0:
            details.append(f"{label} improved by {delta:.4f}.")
        elif delta < 0:
            details.append(f"{label} changed by {delta:.4f}, inside the allowed regression.")
        else:
            details.append(f"{label} is unchanged.")
    return RuleResult(
        metric=metric,
        label=label,
        status=status,  # type: ignore[arg-type]
        baseline=baseline,
        candidate=candidate,
        delta=delta,
        delta_percent=None,
        delta_kind="points",
        unit="ratio",
        detail=" ".join(details),
    )


def _lower_is_better(
    rule: MetricRule,
    baseline: Optional[float],
    candidate: Optional[float],
    label: str,
    metric: str,
    unit: Literal["milliseconds", "usd"],
) -> RuleResult:
    if candidate is None:
        result = _missing(rule, f"{label} was not measured. It was not invented.")
        result.metric = metric
        result.label = label
        result.unit = unit
        result.delta_kind = "relative"
        return result

    status = "pass"
    details: List[str] = []
    delta = None if baseline is None else candidate - baseline
    delta_percent = None
    if baseline is not None:
        delta_percent = _relative_change(baseline, candidate)

    if rule.maximum is not None and candidate > rule.maximum:
        status = _worse(status, _status_for(rule.severity))
        details.append(f"{label} {candidate:.6g} is above maximum {rule.maximum:.6g}.")

    if baseline is not None and rule.max_increase_percent is not None:
        floor = rule.min_baseline_for_percent
        if floor is not None and baseline < floor:
            # The absolute measurements stay on the rule. The relative percent
            # is omitted so sub-threshold noise is not presented as a change
            # the gate evaluated.
            delta_percent = None
            details.append(
                f"Baseline {label} {baseline:.6g} is below {floor:.6g}, so the percent-increase "
                "rule was not applied. Absolute limits still apply."
            )
        elif delta_percent is None:
            status = _worse(status, "review")
            details.append(
                f"Baseline {label} is 0, so a percent increase is undefined. "
                "The absolute change was not converted into a fake percentage."
            )
        elif delta_percent > rule.max_increase_percent:
            status = _worse(status, _status_for(rule.severity))
            details.append(
                f"{label} increased {delta_percent:.2f}%, above the allowed {rule.max_increase_percent:.2f}%."
            )

    if not details:
        details.append(f"{label} is inside its gate.")
    return RuleResult(
        metric=metric,
        label=label,
        status=status,  # type: ignore[arg-type]
        baseline=baseline,
        candidate=candidate,
        delta=delta,
        delta_percent=delta_percent,
        delta_kind="relative",
        unit=unit,
        detail=" ".join(details),
    )


def _band(
    rule: MetricRule,
    baseline: Optional[float],
    candidate: Optional[float],
    label: str,
    metric: str,
) -> RuleResult:
    if candidate is None:
        result = _missing(rule, f"{label} was not measured.")
        result.metric = metric
        result.label = label
        result.unit = "ratio"
        result.delta_kind = "absolute"
        return result
    if baseline is None:
        return RuleResult(
            metric=metric,
            label=label,
            status="skipped",
            candidate=candidate,
            delta_kind="absolute",
            unit="ratio",
            detail=f"{label} has no baseline to compare. Absolute value was recorded and not gated.",
        )
    delta = candidate - baseline
    status = "pass"
    details: List[str] = []
    if rule.max_increase is not None and delta > rule.max_increase:
        status = _status_for(rule.severity)
        details.append(f"{label} increased by {delta:.4f}, above {rule.max_increase:.4f}.")
    if rule.max_decrease is not None and (-delta) > rule.max_decrease:
        status = _worse(status, _status_for(rule.severity))
        details.append(f"{label} decreased by {-delta:.4f}, above {rule.max_decrease:.4f}.")
    if not details:
        details.append(f"{label} stayed inside its allowed band.")
    return RuleResult(
        metric=metric,
        label=label,
        status=status,  # type: ignore[arg-type]
        baseline=baseline,
        candidate=candidate,
        delta=delta,
        delta_kind="absolute",
        unit="ratio",
        detail=" ".join(details),
    )


def apply_gate(
    baseline: Optional[RunMetrics],
    candidate: RunMetrics,
    config: GateConfig,
    variance: VarianceReport,
    subjective_failures: int = 0,
    development_provider: bool = False,
    candidate_completed: Optional[int] = None,
) -> GateOutcome:
    base = baseline
    rules = [
        _higher_is_better(
            config.accuracy,
            None if base is None else base.accuracy,
            candidate.accuracy,
            "Behavioral accuracy",
            "accuracy",
        ),
        _higher_is_better(
            config.tool_success,
            None if base is None else base.tool_success_rate,
            candidate.tool_success_rate,
            "Tool-call success",
            "tool_success",
        ),
        _lower_is_better(
            config.latency_median_ms,
            None if base is None else base.median_latency_ms,
            candidate.median_latency_ms,
            "Median latency",
            "latency_median_ms",
            "milliseconds",
        ),
        _lower_is_better(
            config.latency_p95_ms,
            None if base is None else base.p95_latency_ms,
            candidate.p95_latency_ms,
            "p95 latency",
            "latency_p95_ms",
            "milliseconds",
        ),
        _lower_is_better(
            config.cost_per_request_usd,
            None if base is None else base.average_cost_usd,
            candidate.average_cost_usd,
            "Cost / request",
            "cost_per_request_usd",
            "usd",
        ),
        _band(
            config.human_review_rate,
            None if base is None else base.human_review_rate,
            candidate.human_review_rate,
            "Human-review rate",
            "human_review_rate",
        ),
    ]

    reasons: List[str] = []
    inconclusive = candidate.completed_cases == 0
    if inconclusive:
        reasons.append(
            "Inconclusive. No agent-completed cases. Infrastructure and provider "
            "errors were not converted into an accuracy of 0."
        )

    for rule in rules:
        if rule.status in ("block", "review"):
            reasons.append(rule.detail)

    if subjective_failures:
        reasons.append(
            f"Subjective LLM judge flagged {subjective_failures} case(s). "
            "A judge score cannot pass or block a release by itself."
        )

    if development_provider:
        reasons.append(
            "This run used MockProvider, a development double. "
            "Development doubles cannot pass a release gate."
        )

    if (not variance.sufficient) and config.review_on_insufficient_trials:
        reasons.append(
            f"Insufficient trials ({variance.trials} < {variance.min_trials}). "
            "Variance was not treated as statistical significance."
        )

    if any(rule.status == "block" for rule in rules) or (
        inconclusive and candidate.infrastructure_errors + candidate.provider_errors > 0
    ):
        # An inconclusive run with only infrastructure/provider failures is a
        # review, not a block that pretends the agent scored zero. A real
        # critical metric miss still blocks.
        if any(rule.status == "block" for rule in rules):
            decision: Literal["pass", "review", "block"] = "block"
        else:
            decision = "review"
    elif any(rule.status == "review" for rule in rules) or subjective_failures or development_provider:
        decision = "review"
    elif (not variance.sufficient) and config.review_on_insufficient_trials:
        decision = "review"
    elif any(rule.status == "pass" for rule in rules):
        decision = "pass"
    else:
        decision = "review"
        reasons.append("No metric produced a pass result, so the release was not marked pass.")

    if development_provider and decision == "pass":
        decision = "review"

    if subjective_failures and decision == "pass":
        decision = "review"

    if not reasons and decision == "pass":
        reasons.append("All gated metrics are inside their thresholds.")

    return GateOutcome(
        decision=decision,
        inconclusive=inconclusive,
        reasons=reasons,
        rules=rules,
        subjective_failures=subjective_failures,
        development_provider=development_provider,
    )
