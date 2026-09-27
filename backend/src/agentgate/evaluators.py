"""Evaluators.

Deterministic evaluators decide pass or fail. The LLM judge is subjective:
its result is stored and can only push a release toward human review.
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence

from agentgate.domain import AgentResponse, EvalCase, EvaluatorResult
from agentgate.providers import ChatMessage, ModelProvider
from agentgate.sandbox import DockerSandbox


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


class ExactMatchEvaluator:
    name = "exact_match"
    kind = "deterministic"

    def evaluate(self, case: EvalCase, response: AgentResponse, latency_ms: Optional[float], cost_usd: Optional[float]) -> EvaluatorResult:
        expected = case.expected_behavior.expected_output
        if expected is None:
            return EvaluatorResult(evaluator=self.name, kind=self.kind, status="skip", detail="No expected output.")
        if _norm(response.output) == _norm(expected):
            return EvaluatorResult(evaluator=self.name, kind=self.kind, status="pass", detail="Output matched.")
        return EvaluatorResult(
            evaluator=self.name,
            kind=self.kind,
            status="fail",
            detail=f"Expected output {expected!r} but got {response.output!r}.",
        )


class BehaviorEvaluator:
    name = "behavior"
    kind = "deterministic"

    def evaluate(self, case: EvalCase, response: AgentResponse, latency_ms: Optional[float], cost_usd: Optional[float]) -> EvaluatorResult:
        expected = case.expected_behavior
        names = [call.name for call in response.tool_calls]
        problems: List[str] = []
        for required in expected.must_call:
            if required not in names:
                problems.append(f"missing required tool {required}")
        for forbidden in expected.must_not_call:
            if forbidden in names:
                problems.append(f"called forbidden tool {forbidden}")
        if expected.call_order and not _is_subsequence(expected.call_order, names):
            problems.append(
                f"tool order {names} does not contain {expected.call_order} in order"
            )
        if expected.expected_outcome is not None and response.outcome != expected.expected_outcome:
            problems.append(
                f"outcome {response.outcome!r} != {expected.expected_outcome!r}"
            )
        notes: List[str] = []
        if expected.latency_threshold_ms is not None:
            if latency_ms is None:
                notes.append("latency threshold was not applied because latency was not measured")
            elif latency_ms > expected.latency_threshold_ms:
                problems.append(
                    f"latency {latency_ms:.2f}ms exceeded {expected.latency_threshold_ms:.2f}ms"
                )
        if expected.cost_threshold_usd is not None:
            if cost_usd is None:
                notes.append("cost threshold was not applied because cost is unavailable")
            elif cost_usd > expected.cost_threshold_usd:
                problems.append(
                    f"cost {cost_usd:.6f} exceeded {expected.cost_threshold_usd:.6f}"
                )
        if not any(
            [
                expected.must_call,
                expected.must_not_call,
                expected.call_order,
                expected.expected_outcome,
                expected.latency_threshold_ms is not None,
                expected.cost_threshold_usd is not None,
            ]
        ):
            return EvaluatorResult(evaluator=self.name, kind=self.kind, status="skip", detail="No behavior checks.")
        detail = "; ".join(problems + notes) if (problems or notes) else "Behavior matched."
        if problems:
            return EvaluatorResult(evaluator=self.name, kind=self.kind, status="fail", detail=detail)
        return EvaluatorResult(evaluator=self.name, kind=self.kind, status="pass", detail=detail)


class CodeTestEvaluator:
    name = "code_test"
    kind = "deterministic"

    def __init__(self, sandbox: Optional[DockerSandbox] = None) -> None:
        self.sandbox = sandbox or DockerSandbox()

    def evaluate(self, case: EvalCase, response: AgentResponse, latency_ms: Optional[float], cost_usd: Optional[float]) -> EvaluatorResult:
        spec = case.expected_behavior.deterministic_test
        if spec is None:
            return EvaluatorResult(evaluator=self.name, kind=self.kind, status="skip", detail="No code test.")
        result = self.sandbox.run(
            spec.source,
            {
                "outcome": response.outcome,
                "output": response.output,
                "tool_calls": [call.model_dump() for call in response.tool_calls],
            },
        )
        if result.status == "infrastructure_error":
            return EvaluatorResult(
                evaluator=self.name,
                kind=self.kind,
                status="infrastructure_error",
                detail=result.detail,
            )
        if result.status == "pass":
            return EvaluatorResult(evaluator=self.name, kind=self.kind, status="pass", detail=result.detail)
        return EvaluatorResult(evaluator=self.name, kind=self.kind, status="fail", detail=result.detail)


class LLMJudgeEvaluator:
    name = "llm_judge"
    kind = "subjective"

    def __init__(self, provider: Optional[ModelProvider] = None) -> None:
        self.provider = provider

    def evaluate(self, case: EvalCase, response: AgentResponse, latency_ms: Optional[float], cost_usd: Optional[float]) -> EvaluatorResult:
        rubric = case.expected_behavior.llm_judge
        if rubric is None:
            return EvaluatorResult(evaluator=self.name, kind=self.kind, status="skip", detail="No LLM judge rubric.")
        if self.provider is None:
            return EvaluatorResult(
                evaluator=self.name,
                kind=self.kind,
                status="not_run",
                detail="LLM judge was not run. No judge provider is configured. This does not fail the case.",
            )
        prompt = (
            "You are a subjective judge. Reply with PASS or FAIL and one sentence.\n"
            f"Rubric: {rubric.rubric}\n"
            f"Agent output: {response.output}\n"
        )
        try:
            completion = self.provider.complete(
                [ChatMessage(role="user", content=prompt)],
                tools=[],
                model=self.provider.default_model,
            )
        except Exception as exc:  # provider errors stay subjective, not agent failures
            return EvaluatorResult(
                evaluator=self.name,
                kind=self.kind,
                status="provider_error",
                detail=f"LLM judge provider error: {exc}",
            )
        text = completion.text.strip()
        upper = text.upper()
        if upper.startswith("PASS"):
            return EvaluatorResult(evaluator=self.name, kind=self.kind, status="pass", detail=text)
        if upper.startswith("FAIL"):
            return EvaluatorResult(evaluator=self.name, kind=self.kind, status="fail", detail=text)
        return EvaluatorResult(
            evaluator=self.name,
            kind=self.kind,
            status="provider_error",
            detail=f"LLM judge returned an unparseable verdict: {text!r}",
        )


def _is_subsequence(expected: Sequence[str], actual: Sequence[str]) -> bool:
    index = 0
    for name in actual:
        if index < len(expected) and name == expected[index]:
            index += 1
    return index == len(expected)


def aggregate_status(results: Sequence[EvaluatorResult]) -> str:
    deterministic = [item for item in results if item.kind == "deterministic" and item.status != "skip"]
    if any(item.status == "infrastructure_error" for item in deterministic):
        return "infrastructure_error"
    if any(item.status == "provider_error" for item in deterministic):
        return "provider_error"
    if not deterministic:
        return "infrastructure_error"
    if any(item.status == "fail" for item in deterministic):
        return "failed"
    if all(item.status == "pass" for item in deterministic):
        return "passed"
    return "infrastructure_error"
