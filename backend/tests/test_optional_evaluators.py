from agentgate.domain import DeterministicTest, EvalCase, ExpectedBehavior
from agentgate.engine import evaluate
from agentgate.gates import GateConfig, MetricRule
from agentgate.pricing import PricingTable
from agentgate.providers import ModelProvider, ProviderCompletion
from agentgate.sandbox import SandboxResult
from tests.conftest import ScriptedAgent, dataset, ref


class _Sandbox:
    def __init__(self, status: str, detail: str) -> None:
        self.status = status
        self.detail = detail

    def run(self, source: str, payload: dict) -> SandboxResult:
        return SandboxResult(status=self.status, detail=self.detail)


class _Judge(ModelProvider):
    name = "mock"
    provider_class = "development_double"
    default_model = "mock-judge"

    def __init__(self, text: str) -> None:
        self.text = text

    def complete(self, messages, tools, model):
        return ProviderCompletion(text=self.text)


def _case_with_test() -> EvalCase:
    return EvalCase(
        id="code-1",
        input="code",
        expected_behavior=ExpectedBehavior(
            expected_outcome="ok",
            expected_output="ok",
            deterministic_test=DeterministicTest(source="assert outcome == 'ok'"),
        ),
    )


def test_code_evaluator_docker_failure_is_infrastructure():
    report = evaluate(
        dataset=dataset(_case_with_test()),
        candidate=ScriptedAgent(),
        candidate_ref=ref(),
        gates=GateConfig(accuracy=MetricRule(on_missing="review")),
        pricing=PricingTable(),
        project="unit",
        sandbox=_Sandbox("infrastructure_error", "Docker failed to start"),
    )
    assert report.candidate_metrics.failed_cases == 0
    assert report.candidate_metrics.infrastructure_errors == 1
    assert report.candidate_metrics.accuracy is None
    assert report.gate.decision == "review"
    detail = report.case_results[0].evaluator_results
    code = next(item for item in detail if item.evaluator == "code_test")
    assert code.status == "infrastructure_error"
    assert "Docker failed to start" in code.detail


def test_failing_code_test_is_an_agent_failure():
    report = evaluate(
        dataset=dataset(_case_with_test()),
        candidate=ScriptedAgent(),
        candidate_ref=ref(),
        gates=GateConfig(accuracy=MetricRule(minimum=1, severity="critical", on_missing="review")),
        pricing=PricingTable(),
        project="unit",
        sandbox=_Sandbox("fail", "assertion failed"),
    )
    assert report.candidate_metrics.failed_cases == 1
    assert report.candidate_metrics.accuracy == 0
    assert report.gate.decision == "block"


def test_llm_judge_failure_requests_review_and_does_not_change_accuracy():
    data = dataset(
        EvalCase(
            id="tone",
            input="hello",
            expected_behavior=ExpectedBehavior(
                expected_outcome="ok",
                expected_output="ok",
                llm_judge={"rubric": "The reply should be specific."},
            ),
        )
    )
    report = evaluate(
        dataset=data,
        candidate=ScriptedAgent(),
        candidate_ref=ref(),
        gates=GateConfig(
            accuracy=MetricRule(minimum=0.5, severity="critical"),
            tool_success=MetricRule(on_missing="skip"),
        ),
        pricing=PricingTable(),
        project="unit",
        judge_provider=_Judge("FAIL The reply is too vague."),
    )
    assert report.candidate_metrics.accuracy == 1
    assert report.gate.decision == "review"
    assert report.gate.subjective_failures == 1
    judge = next(item for item in report.case_results[0].evaluator_results if item.evaluator == "llm_judge")
    assert judge.kind == "subjective"
    assert judge.status == "fail"
