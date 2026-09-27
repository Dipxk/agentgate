import pytest

from agentgate.agent import Harness, execute_tool
from agentgate.catalog import demo_catalog
from agentgate.domain import AgentResponse, EvalCase, ExpectedBehavior, ToolCall
from agentgate.errors import InfrastructureError
from agentgate.evaluators import BehaviorEvaluator, EvaluatorResult, ExactMatchEvaluator, aggregate_status


def _response(outcome: str, tools: list) -> AgentResponse:
    return AgentResponse(
        output=outcome,
        outcome=outcome,
        tool_calls=[ToolCall(name=name, arguments={}, latency_ms=0.1) for name in tools],
        provider="policy",
        provider_class="deterministic_harness",
        needs_human_review=False,
    )


def test_exact_match_passes_when_the_text_matches():
    case = EvalCase(
        id="c",
        input="hi",
        expected_behavior=ExpectedBehavior(
            expected_outcome="refund approved",
            expected_output="refund approved",
            must_not_call=["approve_refund"],
        ),
    )
    response = _response("refund approved", [])
    assert ExactMatchEvaluator().evaluate(case, response, 1, None).status == "pass"
    assert BehaviorEvaluator().evaluate(case, response, 1, None).status == "pass"


def test_tool_call_violation_is_detected():
    case = EvalCase(
        id="c",
        input="status",
        expected_behavior=ExpectedBehavior(
            must_call=["get_order"],
            must_not_call=["create_return"],
            expected_outcome="order_status",
        ),
    )
    result = BehaviorEvaluator().evaluate(case, _response("order_status", ["create_return"]), 1, None)
    assert result.status == "fail"
    assert "missing required tool get_order" in result.detail
    assert "forbidden tool create_return" in result.detail


def test_subjective_failure_does_not_fail_the_case():
    status = aggregate_status(
        [
            EvaluatorResult(evaluator="behavior", kind="deterministic", status="pass", detail="ok"),
            EvaluatorResult(evaluator="llm_judge", kind="subjective", status="fail", detail="tone"),
        ]
    )
    assert status == "passed"


def test_unknown_tool_is_refused():
    with pytest.raises(InfrastructureError, match="unknown tool"):
        execute_tool("os.system", {"cmd": "echo hi"}, demo_catalog(), Harness())
