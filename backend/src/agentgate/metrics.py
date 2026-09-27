"""Metric definitions.

Accuracy uses only cases the agent completed. Infrastructure and provider
errors are excluded from the numerator and the denominator.

Latency percentiles use linear interpolation between closest ranks
(the same definition as NumPy's percentile with interpolation "linear").
They are descriptive. They are not confidence intervals.
"""

from __future__ import annotations

import math
import statistics
from typing import List, Optional, Sequence

from agentgate.domain import CaseResult, RunMetrics


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    if p < 0 or p > 100:
        raise ValueError("percentile must be between 0 and 100")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (p / 100.0)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[int(rank)]
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _behavior_passed(result: CaseResult) -> Optional[bool]:
    behavior = [
        item
        for item in result.evaluator_results
        if item.evaluator == "behavior" and item.status != "skip"
    ]
    if not behavior:
        return None
    return all(item.status == "pass" for item in behavior)


def summarize(results: Sequence[CaseResult], total_cases: int) -> RunMetrics:
    completed = [item for item in results if item.status in ("passed", "failed")]
    passed = [item for item in completed if item.status == "passed"]
    failed = [item for item in completed if item.status == "failed"]
    infra = [item for item in results if item.status == "infrastructure_error"]
    provider = [item for item in results if item.status == "provider_error"]

    accuracy = (len(passed) / len(completed)) if completed else None

    latencies = [item.latency_ms for item in completed if item.latency_ms is not None]
    median_latency = statistics.median(latencies) if latencies else None
    p95_latency = percentile(latencies, 95) if latencies else None

    measured_costs = [
        item.cost_usd
        for item in completed
        if item.cost_status == "measured" and item.cost_usd is not None
    ]
    if not completed or not measured_costs:
        cost_status = "unavailable"
        average_cost = None
    elif len(measured_costs) < len(completed):
        cost_status = "partial"
        average_cost = sum(measured_costs) / len(measured_costs)
    else:
        cost_status = "measured"
        average_cost = sum(measured_costs) / len(measured_costs)

    tool_flags: List[bool] = []
    for item in completed:
        flag = _behavior_passed(item)
        if flag is not None:
            tool_flags.append(flag)
    tool_success = (sum(1 for flag in tool_flags if flag) / len(tool_flags)) if tool_flags else None

    review_flags = [item.needs_human_review for item in completed if item.needs_human_review is not None]
    if completed and len(review_flags) == len(completed):
        human_review = sum(1 for flag in review_flags if flag) / len(review_flags)
    else:
        human_review = None

    return RunMetrics(
        total_cases=total_cases,
        completed_cases=len(completed),
        passed_cases=len(passed),
        failed_cases=len(failed),
        infrastructure_errors=len(infra),
        provider_errors=len(provider),
        accuracy=accuracy,
        median_latency_ms=median_latency,
        p95_latency_ms=p95_latency,
        average_cost_usd=average_cost,
        cost_status=cost_status,  # type: ignore[arg-type]
        tool_success_rate=tool_success,
        human_review_rate=human_review,
    )
