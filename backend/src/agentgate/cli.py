"""AgentGate command line."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from sqlalchemy import select

from agentgate import __version__
from agentgate.config import find_repo_root, load_agent_spec, load_dataset, load_gates, load_pricing, load_project_config
from agentgate.domain import EvaluationReport
from agentgate.errors import AgentGateError
from agentgate.gates import apply_gate
from agentgate.github_api import build_comment, post_pull_request_comment
from agentgate.service import replay_project, run_project
from agentgate.storage import RunRow, make_session_factory, save_project, save_run
from agentgate.variance import summarize_trials

app = typer.Typer(add_completion=False, no_args_is_help=True, help="CI/CD release gates for AI agents.")


def _fail(exc: Exception) -> None:
    typer.echo(f"error: {exc}", err=True)
    raise typer.Exit(code=2)


@app.command()
def version() -> None:
    """Print the AgentGate version."""

    typer.echo(__version__)


@app.command()
def init(directory: Path = typer.Argument(Path("."))) -> None:
    """Create a starter .agentgate/config.yaml if one does not exist."""

    target = directory / ".agentgate"
    target.mkdir(parents=True, exist_ok=True)
    config = target / "config.yaml"
    if config.exists():
        typer.echo(f"Already exists: {config}")
        return
    config.write_text(
        "\n".join(
            [
                "project: my-agent",
                "dataset: evaluation/datasets/support_demo.yaml",
                "gates: evaluation/gates/default.yaml",
                "pricing: evaluation/pricing.yaml",
                "baseline: evaluation/agents/baseline.yaml",
                "candidate: evaluation/agents/fixed.yaml",
                "trials: 1",
                "seed: 1",
                "case_timeout_s: 30",
                "",
            ]
        )
    )
    typer.echo(f"Wrote {config}")


@app.command()
def validate(config: Path = typer.Option(Path(".agentgate/config.yaml"), "--config", "-c")) -> None:
    """Load the project files and report configuration errors."""

    try:
        root = find_repo_root(config.parent)
        project = load_project_config(config)
        dataset = load_dataset(root / project.dataset)
        load_gates(root / project.gates)
        load_pricing(root / project.pricing)
        load_agent_spec(root / project.baseline)
        load_agent_spec(root / project.candidate)
    except AgentGateError as exc:
        _fail(exc)
    typer.echo(f"valid: {project.project} ({len(dataset.cases)} cases)")


@app.command()
def evaluate(
    config: Path = typer.Option(Path(".agentgate/config.yaml"), "--config", "-c"),
    baseline: Optional[Path] = typer.Option(None, "--baseline"),
    candidate: Optional[Path] = typer.Option(None, "--candidate"),
    trials: Optional[int] = typer.Option(None, "--trials"),
    seed: Optional[int] = typer.Option(None, "--seed"),
    out: Optional[Path] = typer.Option(None, "--out"),
    baseline_commit: Optional[str] = typer.Option(None, "--baseline-commit"),
    candidate_commit: Optional[str] = typer.Option(None, "--candidate-commit"),
    keep_going: bool = typer.Option(False, "--keep-going", help="Return exit code 0 even when the decision is block."),
) -> None:
    """Evaluate a candidate agent against a baseline on the same dataset."""

    try:
        report = run_project(
            config_path=config,
            baseline_path=baseline,
            candidate_path=candidate,
            trials=trials,
            seed=seed,
            baseline_commit=baseline_commit,
            candidate_commit=candidate_commit,
        )
    except AgentGateError as exc:
        _fail(exc)
    typer.echo(report.text)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report.model_dump_json(indent=2))
        typer.echo(f"\nWrote {out}")
    if report.gate.decision == "block" and not keep_going:
        raise typer.Exit(code=1)


@app.command()
def gate(
    report_path: Path = typer.Argument(..., help="Evaluation report JSON."),
    gates: Optional[Path] = typer.Option(None, "--gates"),
) -> None:
    """Print the decision in a report, or re-apply a gate file to its metrics."""

    try:
        report = EvaluationReport.model_validate_json(report_path.read_text())
        if gates is not None:
            config = load_gates(gates)
            outcome = apply_gate(
                report.baseline_metrics,
                report.candidate_metrics,
                config,
                summarize_trials(
                    [report.candidate_metrics.accuracy],
                    config.min_trials,
                ),
                subjective_failures=report.gate.subjective_failures,
                development_provider=report.gate.development_provider,
            )
            report.gate = outcome
            from agentgate.report import render_report

            report.text = render_report(report)
    except AgentGateError as exc:
        _fail(exc)
    except Exception as exc:
        _fail(exc)
    typer.echo(report.text)
    if report.gate.decision == "block":
        raise typer.Exit(code=1)


@app.command()
def compare(
    left: Path = typer.Argument(..., help="First report JSON."),
    right: Path = typer.Argument(..., help="Second report JSON."),
) -> None:
    """Show candidate measurements from two stored reports. Does not emit a new decision."""

    try:
        first = EvaluationReport.model_validate_json(left.read_text())
        second = EvaluationReport.model_validate_json(right.read_text())
    except Exception as exc:
        _fail(exc)
    typer.echo("AgentGate compare")
    typer.echo("Stored measurements only. This command does not create a release decision.")
    typer.echo("")
    _print_pair("Run", first.manifest.run_id, second.manifest.run_id)
    _print_pair("Decision already recorded", first.gate.decision, second.gate.decision)
    _print_pair("Accuracy", _fmt(first.candidate_metrics.accuracy), _fmt(second.candidate_metrics.accuracy))
    _print_pair(
        "Median latency ms",
        _fmt(first.candidate_metrics.median_latency_ms),
        _fmt(second.candidate_metrics.median_latency_ms),
    )
    _print_pair(
        "Cost / request",
        _fmt(first.candidate_metrics.average_cost_usd),
        _fmt(second.candidate_metrics.average_cost_usd),
    )


@app.command()
def replay(
    report_path: Path = typer.Argument(...),
    config: Path = typer.Option(Path(".agentgate/config.yaml"), "--config", "-c"),
    out: Optional[Path] = typer.Option(None, "--out"),
) -> None:
    """Rerun a stored evaluation with the same dataset, harness, and seed."""

    try:
        original = EvaluationReport.model_validate_json(report_path.read_text())
        report = replay_project(original, config_path=config)
    except AgentGateError as exc:
        _fail(exc)
    except Exception as exc:
        _fail(exc)
    typer.echo(report.text)
    if out:
        out.write_text(report.model_dump_json(indent=2))


@app.command()
def comment(
    report_path: Path = typer.Argument(...),
    dashboard_url: Optional[str] = typer.Option(None, "--dashboard-url"),
    repository: Optional[str] = typer.Option(None, "--repository"),
    pull_request: Optional[int] = typer.Option(None, "--pull-request"),
    post: bool = typer.Option(False, "--post"),
) -> None:
    """Render the pull-request comment. Post it only when --post is set."""

    try:
        report = EvaluationReport.model_validate_json(report_path.read_text())
        body = build_comment(report, dashboard_url)
        if post:
            if repository is None or pull_request is None:
                _fail(AgentGateError("--repository and --pull-request are required with --post"))
            post_pull_request_comment(repository, pull_request, body)
            typer.echo("Posted the comment to GitHub.")
        else:
            typer.echo(body)
    except AgentGateError as exc:
        _fail(exc)


@app.command()
def demo(
    database: Optional[str] = typer.Option(None, "--database"),
) -> None:
    """Run the demonstration story and store the measured reports."""

    root = find_repo_root()
    factory = make_session_factory(database)
    with factory() as existing_db:
        if existing_db.scalar(select(RunRow.id).limit(1)):
            typer.echo("Demonstration runs already stored.")
            return
    created = datetime.now(timezone.utc).isoformat()
    scenarios = [
        ("regressed", "Break: late returns are approved."),
        ("fixed", "Fix: the window is inclusive and late returns are refused."),
        ("cautious", "Tradeoff: behavior is fixed, and more cases are sent to a person."),
    ]
    with factory() as db:
        project = save_project(
            db,
            name="support-demo",
            description=(
                "Demonstration customer-support harness. The catalog and cases are synthetic. "
                "Measurements come from executing the harness, not from hardcoded scores."
            ),
            config={
                "dataset": "evaluation/datasets/support_demo.yaml",
                "gates": "evaluation/gates/default.yaml",
                "pricing": "evaluation/pricing.yaml",
                "versions": [
                    {"name": "baseline", "path": "evaluation/agents/baseline.yaml", "role": "production"},
                    {"name": "regressed", "path": "evaluation/agents/regressed.yaml", "role": "candidate"},
                    {"name": "fixed", "path": "evaluation/agents/fixed.yaml", "role": "candidate"},
                    {"name": "cautious", "path": "evaluation/agents/cautious.yaml", "role": "candidate"},
                ],
            },
            created_at=created,
        )
        for name, blurb in scenarios:
            try:
                report = run_project(
                    root=root,
                    candidate_path=root / "evaluation" / "agents" / f"{name}.yaml",
                    candidate_commit=name,
                    baseline_commit="baseline",
                )
            except AgentGateError as exc:
                _fail(exc)
            save_run(db, project.id, report)
            accuracy = report.candidate_metrics.accuracy
            baseline_accuracy = None if report.baseline_metrics is None else report.baseline_metrics.accuracy
            typer.echo(blurb)
            typer.echo(
                f"  {name}: baseline {_pct(baseline_accuracy)} -> candidate {_pct(accuracy)}  "
                f"decision {report.gate.decision.upper()}  run {report.manifest.run_id}"
            )
    typer.echo("Stored the demonstration runs. Start the API with: agentgate serve")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    """Start the HTTP API."""

    import uvicorn

    uvicorn.run("agentgate.api:app", host=host, port=port)


def _pct(value: Optional[float]) -> str:
    if value is None:
        return "not measured"
    return f"{value * 100:.1f}%"


def _fmt(value: Optional[float]) -> str:
    if value is None:
        return "not measured"
    return f"{value:.6g}"


def _print_pair(label: str, left: str, right: str) -> None:
    typer.echo(f"{label:<28} {left:<18} {right}")


if __name__ == "__main__":
    app()
