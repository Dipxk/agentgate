"""Evaluation orchestrator.

The web API, the CLI, and GitHub Actions all call this module. Metric math
is not reimplemented at the edges.
"""

from __future__ import annotations

import platform
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol

from agentgate import EVALUATOR_VERSION, __version__
from agentgate.catalog import canonical_hash, demo_catalog
from agentgate.domain import (
    AgentResponse,
    CaseComparison,
    CaseResult,
    Dataset,
    EvalCase,
    EvaluationReport,
    RunManifest,
    VersionRef,
)
from agentgate.errors import InfrastructureError, ProviderError
from agentgate.evaluators import (
    BehaviorEvaluator,
    CodeTestEvaluator,
    ExactMatchEvaluator,
    LLMJudgeEvaluator,
    aggregate_status,
)
from agentgate.gates import GateConfig, apply_gate
from agentgate.log import RunLog
from agentgate.metrics import summarize
from agentgate.pricing import PricingTable, estimate_cost
from agentgate.providers import ModelProvider
from agentgate.report import render_report
from agentgate.sandbox import DockerSandbox
from agentgate.variance import summarize_trials


class Runnable(Protocol):
    provider: str
    provider_class: str
    model: Optional[str]
    execution_mode: str

    def run(self, case_input: str) -> AgentResponse:
        ...


def environment_fingerprint(catalog_hash: str) -> Dict[str, Any]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "agentgate": __version__,
        "evaluator": EVALUATOR_VERSION,
        "catalog_hash": catalog_hash,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_with_timeout(agent: Runnable, case_input: str, timeout_s: float) -> AgentResponse:
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(agent.run, case_input)
    try:
        return future.result(timeout=timeout_s)
    except FuturesTimeout as exc:
        raise InfrastructureError(f"Agent exceeded the {timeout_s}s case timeout.") from exc
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _failure_result(
    case: EvalCase,
    side: str,
    trial: int,
    status: str,
    failure_class: str,
    error: str,
) -> CaseResult:
    return CaseResult(
        case_id=case.id,
        case_input=case.input,
        expected_outcome=case.expected_behavior.expected_outcome,
        expected_output=case.expected_behavior.expected_output,
        must_call=list(case.expected_behavior.must_call),
        must_not_call=list(case.expected_behavior.must_not_call),
        side=side,  # type: ignore[arg-type]
        trial=trial,
        status=status,  # type: ignore[arg-type]
        failure_class=failure_class,  # type: ignore[arg-type]
        error=error,
        cost_status="unavailable",
    )


def _execute_case(
    case: EvalCase,
    agent: Runnable,
    side: str,
    trial: int,
    pricing: PricingTable,
    timeout_s: float,
    log: RunLog,
    exact: ExactMatchEvaluator,
    behavior: BehaviorEvaluator,
    code: CodeTestEvaluator,
    judge: LLMJudgeEvaluator,
) -> CaseResult:
    log.event("case_start", case_id=case.id, side=side, trial=trial)
    started = time.perf_counter()
    try:
        response = _run_with_timeout(agent, case.input, timeout_s)
    except ProviderError as exc:
        log.event("case_completion", case_id=case.id, side=side, status="provider_error", level="error")
        return _failure_result(case, side, trial, "provider_error", "provider", str(exc))
    except InfrastructureError as exc:
        log.event("case_completion", case_id=case.id, side=side, status="infrastructure_error", level="error")
        return _failure_result(case, side, trial, "infrastructure_error", "infrastructure", str(exc))
    except Exception as exc:
        log.event(
            "case_completion",
            case_id=case.id,
            side=side,
            status="infrastructure_error",
            level="error",
            error=type(exc).__name__,
        )
        return _failure_result(
            case,
            side,
            trial,
            "infrastructure_error",
            "infrastructure",
            f"Unhandled runner error ({type(exc).__name__}): {exc}",
        )

    latency_ms = (time.perf_counter() - started) * 1000
    if response.model_latency_ms is not None:
        log.event(
            "model_call",
            case_id=case.id,
            side=side,
            provider=response.provider,
            model=response.model,
            latency_ms=response.model_latency_ms,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
    for call in response.tool_calls:
        log.event(
            "tool_call",
            case_id=case.id,
            side=side,
            tool=call.name,
            latency_ms=call.latency_ms,
            error=call.error,
        )

    cost = estimate_cost(response.input_tokens, response.output_tokens, response.model, pricing)
    eval_started = time.perf_counter()
    evaluations = [
        exact.evaluate(case, response, latency_ms, cost),
        behavior.evaluate(case, response, latency_ms, cost),
        code.evaluate(case, response, latency_ms, cost),
        judge.evaluate(case, response, latency_ms, cost),
    ]
    evaluation_latency = (time.perf_counter() - eval_started) * 1000
    status = aggregate_status(evaluations)
    failure_class = None
    if status == "failed":
        failure_class = "agent"
    elif status == "infrastructure_error":
        failure_class = "infrastructure"
    elif status == "provider_error":
        failure_class = "provider"

    for item in evaluations:
        log.event(
            "evaluator_result",
            case_id=case.id,
            side=side,
            evaluator=item.evaluator,
            kind=item.kind,
            status=item.status,
        )
    log.event("case_completion", case_id=case.id, side=side, status=status, latency_ms=latency_ms)

    tool_latency = sum(call.latency_ms for call in response.tool_calls) if response.tool_calls else 0.0
    return CaseResult(
        case_id=case.id,
        case_input=case.input,
        expected_outcome=case.expected_behavior.expected_outcome,
        expected_output=case.expected_behavior.expected_output,
        must_call=list(case.expected_behavior.must_call),
        must_not_call=list(case.expected_behavior.must_not_call),
        side=side,  # type: ignore[arg-type]
        trial=trial,
        status=status,  # type: ignore[arg-type]
        failure_class=failure_class,  # type: ignore[arg-type]
        output=response.output,
        outcome=response.outcome,
        tool_calls=response.tool_calls,
        evaluator_results=evaluations,
        latency_ms=latency_ms,
        model_latency_ms=response.model_latency_ms,
        tool_latency_ms=tool_latency,
        evaluation_latency_ms=evaluation_latency,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cost_usd=cost,
        cost_status="measured" if cost is not None else "unavailable",
        needs_human_review=response.needs_human_review,
    )


def _comparisons(results: List[CaseResult]) -> List[CaseComparison]:
    baseline = {item.case_id: item for item in results if item.side == "baseline" and item.trial == 1}
    candidate = {item.case_id: item for item in results if item.side == "candidate" and item.trial == 1}
    compared: List[CaseComparison] = []
    for case_id in candidate:
        base = baseline.get(case_id)
        cand = candidate[case_id]
        change = "unchanged"
        if base is None:
            change = "unscored" if cand.status not in ("passed", "failed") else "unchanged"
        elif base.status not in ("passed", "failed") or cand.status not in ("passed", "failed"):
            change = "unscored"
        elif base.status == "passed" and cand.status == "failed":
            change = "regression"
        elif base.status == "failed" and cand.status == "passed":
            change = "fix"
        compared.append(
            CaseComparison(
                case_id=case_id,
                baseline_status=None if base is None else base.status,
                candidate_status=cand.status,
                baseline_outcome=None if base is None else base.outcome,
                candidate_outcome=cand.outcome,
                change=change,  # type: ignore[arg-type]
            )
        )
    return compared


def _subjective_failures(results: List[CaseResult]) -> int:
    count = 0
    for result in results:
        if result.side != "candidate" or result.trial != 1:
            continue
        for item in result.evaluator_results:
            if item.kind == "subjective" and item.status == "fail":
                count += 1
    return count


def evaluate(
    dataset: Dataset,
    candidate: Runnable,
    candidate_ref: VersionRef,
    gates: GateConfig,
    pricing: PricingTable,
    project: str,
    baseline: Optional[Runnable] = None,
    baseline_ref: Optional[VersionRef] = None,
    trials: int = 1,
    seed: Optional[int] = None,
    case_timeout_s: float = 30.0,
    dataset_path: Optional[str] = None,
    judge_provider: Optional[ModelProvider] = None,
    sandbox: Optional[DockerSandbox] = None,
    log_stream: Optional[Any] = None,
    run_id: Optional[str] = None,
) -> EvaluationReport:
    if trials < 1:
        raise InfrastructureError("trials must be >= 1")
    identifier = run_id or uuid.uuid4().hex
    log = RunLog(identifier, stream=log_stream)
    catalog_hash = demo_catalog().fingerprint()
    manifest = RunManifest(
        run_id=identifier,
        project=project,
        dataset_name=dataset.name,
        dataset_version=dataset.version,
        dataset_hash=canonical_hash(dataset.model_dump(mode="json")),
        dataset_path=dataset_path,
        evaluator_version=EVALUATOR_VERSION,
        agentgate_version=__version__,
        seed=seed,
        trials=trials,
        environment=environment_fingerprint(catalog_hash),
        baseline=baseline_ref,
        candidate=candidate_ref,
        started_at=_now(),
    )
    log.event(
        "evaluation_start",
        project=project,
        dataset=dataset.name,
        dataset_hash=manifest.dataset_hash,
        trials=trials,
        seed=seed,
        baseline=None if baseline_ref is None else baseline_ref.name,
        candidate=candidate_ref.name,
    )

    exact = ExactMatchEvaluator()
    behavior = BehaviorEvaluator()
    code = CodeTestEvaluator(sandbox or DockerSandbox())
    judge = LLMJudgeEvaluator(judge_provider)
    results: List[CaseResult] = []

    for trial in range(1, trials + 1):
        for case in dataset.cases:
            if baseline is not None:
                results.append(
                    _execute_case(
                        case, baseline, "baseline", trial, pricing, case_timeout_s, log, exact, behavior, code, judge
                    )
                )
            results.append(
                _execute_case(
                    case, candidate, "candidate", trial, pricing, case_timeout_s, log, exact, behavior, code, judge
                )
            )

    candidate_results = [item for item in results if item.side == "candidate"]
    baseline_results = [item for item in results if item.side == "baseline"]
    candidate_metrics = summarize(candidate_results, total_cases=len(dataset.cases) * trials)
    # Headline counts should describe one pass over the dataset, while pooled
    # rates stay available through the same function. Recompute the displayed
    # counts from trial 1 and keep rates on the pooled sample when trials > 1.
    trial_one = [item for item in candidate_results if item.trial == 1]
    display = summarize(trial_one, total_cases=len(dataset.cases))
    if trials > 1:
        pooled = candidate_metrics
        display.accuracy = pooled.accuracy
        display.tool_success_rate = pooled.tool_success_rate
        display.human_review_rate = pooled.human_review_rate
        display.median_latency_ms = pooled.median_latency_ms
        display.p95_latency_ms = pooled.p95_latency_ms
        display.average_cost_usd = pooled.average_cost_usd
        display.cost_status = pooled.cost_status
        display.completed_cases = pooled.completed_cases
        display.passed_cases = pooled.passed_cases
        display.failed_cases = pooled.failed_cases
        display.infrastructure_errors = pooled.infrastructure_errors
        display.provider_errors = pooled.provider_errors
        display.total_cases = pooled.total_cases

    baseline_metrics = summarize(baseline_results, total_cases=len(dataset.cases) * trials) if baseline is not None else None
    if baseline_metrics is not None and trials == 1:
        baseline_metrics = summarize(
            [item for item in baseline_results if item.trial == 1],
            total_cases=len(dataset.cases),
        )

    per_trial = []
    for trial in range(1, trials + 1):
        summary = summarize(
            [item for item in candidate_results if item.trial == trial],
            total_cases=len(dataset.cases),
        )
        per_trial.append(summary.accuracy)
    variance = summarize_trials(per_trial, gates.min_trials)
    development = candidate_ref.provider_class == "development_double" or (
        baseline_ref is not None and baseline_ref.provider_class == "development_double"
    )
    gate = apply_gate(
        baseline_metrics,
        display,
        gates,
        variance,
        subjective_failures=_subjective_failures(results),
        development_provider=development,
    )
    manifest.completed_at = _now()
    manifest.status = "completed"
    log.event("evaluation_completion", status="completed")
    log.event("decision", decision=gate.decision, inconclusive=gate.inconclusive, reasons=gate.reasons)

    report = EvaluationReport(
        manifest=manifest,
        baseline_metrics=baseline_metrics,
        candidate_metrics=display,
        gate=gate,
        variance=variance,
        case_results=results,
        comparisons=_comparisons(results),
        logs=log.records,
        text="",
    )
    report.text = render_report(report)
    return report
