"""Release decisions produced by the evaluation engine, not by fixtures in the UI."""

from agentgate.config import load_dataset, load_gates, load_pricing
from agentgate.domain import EvalCase, ExpectedBehavior
from agentgate.engine import evaluate
from agentgate.gates import GateConfig, MetricRule
from agentgate.loader import load_version
from agentgate.pricing import ModelPrice, PricingTable
from agentgate.replay import replay_report
from tests.conftest import ROOT, ScriptedAgent, dataset, infra_error, provider_error, ref


def _demo(candidate: str, trials: int = 1):
    data = load_dataset(ROOT / "evaluation/datasets/support_demo.yaml")
    gates = load_gates(ROOT / "evaluation/gates/default.yaml")
    pricing = load_pricing(ROOT / "evaluation/pricing.yaml")
    _, baseline_ref, baseline = load_version(ROOT / "evaluation/agents/baseline.yaml", commit="baseline")
    _, candidate_ref, agent = load_version(ROOT / "evaluation/agents" / f"{candidate}.yaml", commit=candidate)
    return evaluate(
        dataset=data,
        baseline=baseline,
        baseline_ref=baseline_ref,
        candidate=agent,
        candidate_ref=candidate_ref,
        gates=gates,
        pricing=pricing,
        project="support-demo",
        trials=trials,
        seed=1,
        dataset_path="evaluation/datasets/support_demo.yaml",
    )


def _failed(report, side: str):
    return sorted(
        item.case_id
        for item in report.case_results
        if item.side == side and item.trial == 1 and item.status == "failed"
    )


def test_passing_fixed_agent_passes():
    report = _demo("fixed")
    assert _failed(report, "candidate") == []
    assert report.candidate_metrics.accuracy == 1
    assert report.candidate_metrics.failed_cases == 0
    assert report.gate.decision == "pass"
    assert report.candidate_metrics.cost_status == "unavailable"
    assert report.candidate_metrics.average_cost_usd is None
    assert "not measured" in report.text
    assert report.variance.sufficient is False
    assert report.variance.sample_variance is None


def test_regressed_agent_is_blocked():
    report = _demo("regressed")
    assert _failed(report, "baseline") == ["support-010"]
    assert _failed(report, "candidate") == [
        "support-008",
        "support-009",
        "support-021",
        "support-022",
    ]
    assert report.baseline_metrics.accuracy == 23 / 24
    assert report.candidate_metrics.accuracy == 20 / 24
    assert report.gate.decision == "block"
    regressions = [item.case_id for item in report.comparisons if item.change == "regression"]
    assert regressions == ["support-008", "support-009", "support-021", "support-022"]
    assert any(item.change == "fix" and item.case_id == "support-010" for item in report.comparisons)
    assert report.candidate_metrics.infrastructure_errors == 0
    assert "BLOCK" in report.text


def test_fixed_agent_recovers_against_the_same_baseline():
    report = _demo("fixed")
    assert report.baseline_metrics.accuracy == 23 / 24
    assert report.candidate_metrics.accuracy == 1
    assert report.gate.decision == "pass"
    assert [item.case_id for item in report.comparisons if item.change == "fix"] == ["support-010"]


def test_cautious_agent_requires_review_without_blocking():
    report = _demo("cautious")
    assert report.candidate_metrics.accuracy == 1
    assert report.gate.decision == "review"
    assert report.candidate_metrics.human_review_rate == 4 / 24
    assert report.baseline_metrics.human_review_rate == 1 / 24
    human = next(rule for rule in report.gate.rules if rule.metric == "human_review_rate")
    assert human.status == "review"
    accuracy = next(rule for rule in report.gate.rules if rule.metric == "accuracy")
    assert accuracy.status == "pass"


def test_infrastructure_failure_is_not_an_agent_failure():
    data = dataset(EvalCase(id="a", input="a", expected_behavior=ExpectedBehavior(expected_outcome="ok")))
    gates = GateConfig(accuracy=MetricRule(minimum=0.9, on_missing="review"))
    report = evaluate(
        dataset=data,
        candidate=ScriptedAgent(error=infra_error()),
        candidate_ref=ref(),
        gates=gates,
        pricing=PricingTable(),
        project="unit",
    )
    assert report.candidate_metrics.accuracy is None
    assert report.candidate_metrics.failed_cases == 0
    assert report.candidate_metrics.infrastructure_errors == 1
    assert report.gate.decision == "review"
    assert report.gate.inconclusive is True
    assert "0" not in report.gate.reasons[0] or "not converted into an accuracy of 0" in report.gate.reasons[0]


def test_provider_timeout_is_separate_from_agent_failure():
    data = dataset(EvalCase(id="a", input="a", expected_behavior=ExpectedBehavior(expected_outcome="ok")))
    report = evaluate(
        dataset=data,
        candidate=ScriptedAgent(error=provider_error()),
        candidate_ref=ref("candidate", "model"),
        gates=GateConfig(),
        pricing=PricingTable(),
        project="unit",
    )
    assert report.candidate_metrics.provider_errors == 1
    assert report.candidate_metrics.failed_cases == 0
    assert report.candidate_metrics.accuracy is None


def test_latency_regression_is_detected():
    data = dataset(
        EvalCase(id="a", input="a", expected_behavior=ExpectedBehavior(expected_outcome="ok", expected_output="ok")),
        EvalCase(id="b", input="b", expected_behavior=ExpectedBehavior(expected_outcome="ok", expected_output="ok")),
    )
    gates = GateConfig(
        accuracy=MetricRule(minimum=0.5, max_regression=1, severity="critical"),
        tool_success=MetricRule(on_missing="skip"),
        latency_p95_ms=MetricRule(
            maximum=40,
            max_increase_percent=10,
            min_baseline_for_percent=5,
            severity="critical",
            on_missing="skip",
        ),
    )
    report = evaluate(
        dataset=data,
        baseline=ScriptedAgent(sleep_s=0.01),
        baseline_ref=ref("baseline"),
        candidate=ScriptedAgent(sleep_s=0.07),
        candidate_ref=ref("slow"),
        gates=gates,
        pricing=PricingTable(),
        project="unit",
    )
    latency = next(rule for rule in report.gate.rules if rule.metric == "latency_p95_ms")
    assert report.candidate_metrics.p95_latency_ms is not None
    assert report.candidate_metrics.p95_latency_ms > 40
    assert latency.status == "block"
    assert report.gate.decision == "block"
    accuracy = next(rule for rule in report.gate.rules if rule.metric == "accuracy")
    assert accuracy.status == "pass"


def test_cost_regression_is_detected_from_tokens_and_a_price_table():
    data = dataset(
        EvalCase(id="a", input="a", expected_behavior=ExpectedBehavior(expected_outcome="ok", expected_output="ok"))
    )
    pricing = PricingTable(models={"example-model": ModelPrice(input_per_million=1, output_per_million=1)})
    gates = GateConfig(
        accuracy=MetricRule(minimum=0.5, max_regression=1),
        cost_per_request_usd=MetricRule(max_increase_percent=25, severity="critical", on_missing="skip"),
    )
    report = evaluate(
        dataset=data,
        baseline=ScriptedAgent(tokens=10, model="example-model"),
        baseline_ref=ref("baseline", "model"),
        candidate=ScriptedAgent(tokens=1000, model="example-model"),
        candidate_ref=ref("costly", "model"),
        gates=gates,
        pricing=pricing,
        project="unit",
    )
    assert report.baseline_metrics.average_cost_usd == 20 / 1_000_000
    assert report.candidate_metrics.average_cost_usd == 2000 / 1_000_000
    cost = next(rule for rule in report.gate.rules if rule.metric == "cost_per_request_usd")
    assert cost.status == "block"
    assert report.gate.decision == "block"


def test_missing_price_does_not_invent_a_cost():
    data = dataset(
        EvalCase(id="a", input="a", expected_behavior=ExpectedBehavior(expected_outcome="ok", expected_output="ok"))
    )
    report = evaluate(
        dataset=data,
        candidate=ScriptedAgent(tokens=100, model="unpriced-model"),
        candidate_ref=ref("candidate", "model"),
        gates=GateConfig(),
        pricing=PricingTable(),
        project="unit",
    )
    assert report.candidate_metrics.average_cost_usd is None
    assert report.candidate_metrics.cost_status == "unavailable"


def test_replay_preserves_case_structure(tmp_path):
    report = _demo("fixed")
    replayed = replay_report(
        report,
        ROOT,
        ROOT / "evaluation/gates/default.yaml",
        ROOT / "evaluation/pricing.yaml",
    )
    original = [
        (item.case_id, item.side, item.status, item.outcome, tuple(call.name for call in item.tool_calls))
        for item in report.case_results
    ]
    again = [
        (item.case_id, item.side, item.status, item.outcome, tuple(call.name for call in item.tool_calls))
        for item in replayed.case_results
    ]
    assert original == again
    assert replayed.gate.decision == report.gate.decision
    assert replayed.manifest.dataset_hash == report.manifest.dataset_hash
    assert replayed.manifest.seed == report.manifest.seed
    assert replayed.manifest.run_id != report.manifest.run_id
