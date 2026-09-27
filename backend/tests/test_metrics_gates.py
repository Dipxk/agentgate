import math
from pathlib import Path

import pytest

from agentgate.domain import RunMetrics
from agentgate.gates import GateConfig, MetricRule, apply_gate
from agentgate.metrics import percentile
from agentgate.sandbox import SandboxLimits, docker_argv
from agentgate.variance import sample_variance, summarize_trials


def _metrics(**overrides) -> RunMetrics:
    payload = dict(
        total_cases=10,
        completed_cases=10,
        passed_cases=10,
        failed_cases=0,
        infrastructure_errors=0,
        provider_errors=0,
        accuracy=1.0,
        median_latency_ms=100.0,
        p95_latency_ms=120.0,
        average_cost_usd=0.02,
        cost_status="measured",
        tool_success_rate=1.0,
        human_review_rate=0.1,
    )
    payload.update(overrides)
    return RunMetrics(**payload)


def test_percentile_uses_linear_interpolation():
    values = [float(item) for item in range(1, 11)]
    assert percentile(values, 95) == pytest.approx(9.55)
    assert percentile([5.0], 95) == 5.0


def test_variance_does_not_invent_spread_or_claim_significance():
    single = summarize_trials([0.91], min_trials=5)
    assert single.sufficient is False
    assert single.sample_variance is None
    assert "not a confidence interval" in single.note
    assert "not a test of statistical significance" in single.note

    three = summarize_trials([0.91, 0.90, 0.92], min_trials=5)
    assert three.sufficient is False
    assert three.mean_accuracy == pytest.approx((0.91 + 0.90 + 0.92) / 3)
    assert three.sample_variance == pytest.approx(sample_variance([0.91, 0.90, 0.92]))


def test_equal_trials_report_zero_variance_without_claiming_enough_data():
    report = summarize_trials([0.95, 0.95, 0.95], min_trials=5)
    assert report.sample_variance == 0
    assert report.sufficient is False


def test_accuracy_gain_with_a_large_cost_increase_is_review():
    outcome = apply_gate(
        _metrics(accuracy=0.914, average_cost_usd=0.021),
        _metrics(accuracy=0.942, average_cost_usd=0.037),
        GateConfig(
            accuracy=MetricRule(minimum=0.90, max_regression=0.02, severity="critical"),
            cost_per_request_usd=MetricRule(max_increase_percent=25, severity="review"),
            tool_success=MetricRule(minimum=0.0, max_regression=1),
            latency_p95_ms=MetricRule(on_missing="skip"),
            latency_median_ms=MetricRule(on_missing="skip"),
            human_review_rate=MetricRule(max_increase=1, max_decrease=1, severity="review"),
        ),
        summarize_trials([0.942], min_trials=5),
    )
    assert outcome.decision == "review"
    cost = next(rule for rule in outcome.rules if rule.metric == "cost_per_request_usd")
    accuracy = next(rule for rule in outcome.rules if rule.metric == "accuracy")
    assert accuracy.status == "pass"
    assert cost.status == "review"
    assert cost.delta_percent == pytest.approx((0.037 - 0.021) / 0.021 * 100)


def test_development_double_cannot_pass():
    outcome = apply_gate(
        None,
        _metrics(),
        GateConfig(
            accuracy=MetricRule(minimum=0.5),
            tool_success=MetricRule(minimum=0.5),
            latency_median_ms=MetricRule(maximum=1000, on_missing="skip"),
            latency_p95_ms=MetricRule(maximum=1000, on_missing="skip"),
            cost_per_request_usd=MetricRule(maximum=1, on_missing="skip"),
            human_review_rate=MetricRule(on_missing="skip"),
        ),
        summarize_trials([1.0], min_trials=1),
        development_provider=True,
    )
    assert outcome.decision == "review"
    assert "MockProvider" in " ".join(outcome.reasons)


def test_docker_command_is_unprivileged(tmp_path: Path):
    argv = docker_argv(SandboxLimits(), tmp_path)
    assert "--privileged" not in argv
    assert argv[argv.index("--network") + 1] == "none"
    assert "ALL" in argv
    assert "--read-only" in argv
    assert "no-new-privileges" in argv
    assert "65534:65534" in argv
    assert "docker.sock" not in " ".join(argv)


def test_sample_variance_uses_n_minus_one():
    # Mean of 1, 2, 3 is 2. Sample variance is (1+0+1)/2 = 1.
    assert sample_variance([1.0, 2.0, 3.0]) == pytest.approx(1.0)
    assert sample_variance([1.0]) is None
    assert math.isfinite(sample_variance([1.0, 2.0]))
