"""Text reports for the CLI and GitHub comments.

Numbers are formatted from a measured report. Missing measurements stay missing.
"""

from __future__ import annotations

from typing import Optional

from agentgate.domain import EvaluationReport, RuleResult


def _ratio(value: Optional[float]) -> str:
    if value is None:
        return "not measured"
    return f"{value * 100:.1f}%"


def _ms(value: Optional[float]) -> str:
    if value is None:
        return "not measured"
    if value < 1000:
        return f"{value:.1f}ms"
    return f"{value / 1000:.3f}s"


def _usd(value: Optional[float]) -> str:
    if value is None:
        return "not measured"
    return f"${value:.6f}"


def _format_value(rule: RuleResult, value: Optional[float]) -> str:
    if rule.unit == "ratio":
        return _ratio(value)
    if rule.unit == "milliseconds":
        return _ms(value)
    if rule.unit == "usd":
        return _usd(value)
    if value is None:
        return "not measured"
    return f"{value:.4g}"


def _change(rule: RuleResult) -> str:
    if rule.baseline is None or rule.candidate is None or rule.delta is None:
        return "n/a"
    if rule.delta_kind == "points":
        return f"{rule.delta * 100:+.1f} pp"
    if rule.delta_kind == "relative":
        if rule.delta_percent is None:
            return "n/a"
        return f"{rule.delta_percent:+.1f}%"
    if rule.unit == "ratio":
        return f"{rule.delta * 100:+.1f} pp"
    return f"{rule.delta:+.4g}"


def _mark(status: str) -> str:
    return {
        "pass": "PASS",
        "review": "REVIEW",
        "block": "BLOCK",
        "skipped": "SKIP",
        "not_measured": "N/A",
    }.get(status, status.upper())


def render_report(report: EvaluationReport) -> str:
    lines = ["AgentGate", "────────────", ""]
    manifest = report.manifest
    lines.append(f"Run {manifest.run_id}")
    lines.append(f"Dataset {manifest.dataset_name}@{manifest.dataset_version}  {manifest.dataset_hash[:12]}")
    if manifest.baseline is not None:
        lines.append(
            f"Baseline {manifest.baseline.name} {manifest.baseline.version}  {manifest.baseline.provider}"
            + (f"  {manifest.baseline.commit}" if manifest.baseline.commit else "")
        )
    lines.append(
        f"Candidate {manifest.candidate.name} {manifest.candidate.version}  {manifest.candidate.provider}"
        + (f"  {manifest.candidate.commit}" if manifest.candidate.commit else "")
    )
    lines.append("")
    metrics = report.candidate_metrics
    lines.append(
        f"Cases {metrics.passed_cases} passed, {metrics.failed_cases} failed, "
        f"{metrics.infrastructure_errors} infrastructure, {metrics.provider_errors} provider"
    )
    lines.append("")
    for rule in report.gate.rules:
        left = _format_value(rule, rule.baseline)
        right = _format_value(rule, rule.candidate)
        lines.append(f"{rule.label:<22} {left:>16} -> {right:<16} {_change(rule):>10}  {_mark(rule.status)}")
    lines.append("")
    decision = report.gate.decision.upper()
    if report.gate.inconclusive:
        decision = f"{decision} (INCONCLUSIVE)"
    lines.append(f"Decision: {decision}")
    for reason in report.gate.reasons:
        lines.append(f"- {reason}")
    variance = report.variance
    lines.append("")
    if variance.sufficient:
        trial_label = f"Trials: {variance.trials}"
    else:
        trial_label = f"Trials: {variance.trials} (insufficient trials; {variance.trials} < {variance.min_trials})"
    lines.append(trial_label)
    lines.append(f"Mean accuracy: {_ratio(variance.mean_accuracy)}")
    lines.append(f"Median accuracy: {_ratio(variance.median_accuracy)}")
    if variance.sample_variance is None:
        lines.append("Sample variance: not computed (need at least 2 trials)")
    else:
        lines.append(f"Sample variance: {variance.sample_variance:.6f}")
    lines.append(variance.note)
    return "\n".join(lines)


def render_github_comment(report: EvaluationReport, dashboard_url: Optional[str] = None) -> str:
    body = ["### AgentGate", "", "AI evaluation report", ""]
    body.append("```")
    body.append(render_report(report))
    body.append("```")
    body.append("")
    regressions = [item for item in report.comparisons if item.change == "regression"]
    fixes = [item for item in report.comparisons if item.change == "fix"]
    if regressions:
        body.append("Regressions: " + ", ".join(item.case_id for item in regressions))
    if fixes:
        body.append("Fixes: " + ", ".join(item.case_id for item in fixes))
    if dashboard_url:
        separator = "&" if "?" in dashboard_url else "?"
        body.append("")
        body.append(f"[View full report]({dashboard_url}{separator}run={report.manifest.run_id})")
    else:
        body.append("")
        body.append("Dashboard link: not configured.")
    return "\n".join(body)
