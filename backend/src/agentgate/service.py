"""Run an evaluation from project files. Shared by the CLI and the API."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from agentgate.config import (
    find_repo_root,
    load_dataset,
    load_gates,
    load_pricing,
    load_project_config,
    resolve_inside,
)
from agentgate.domain import EvaluationReport
from agentgate.engine import evaluate
from agentgate.loader import load_version
from agentgate.replay import replay_report


def relative_to_root(root: Path, path: Path) -> str:
    resolved = path.resolve()
    root = root.resolve()
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return str(resolved)


def run_project(
    root: Optional[Path] = None,
    config_path: Optional[Path] = None,
    baseline_path: Optional[Path] = None,
    candidate_path: Optional[Path] = None,
    trials: Optional[int] = None,
    seed: Optional[int] = None,
    baseline_commit: Optional[str] = None,
    candidate_commit: Optional[str] = None,
) -> EvaluationReport:
    root = (root or find_repo_root()).resolve()
    config_file = config_path or (root / ".agentgate" / "config.yaml")
    config = load_project_config(config_file)
    dataset_path = resolve_inside(root, config.dataset)
    gates_path = resolve_inside(root, config.gates)
    pricing_path = resolve_inside(root, config.pricing)
    baseline_file = baseline_path or resolve_inside(root, config.baseline)
    candidate_file = candidate_path or resolve_inside(root, config.candidate)

    _, baseline_ref, baseline = load_version(baseline_file, commit=baseline_commit)
    _, candidate_ref, candidate = load_version(candidate_file, commit=candidate_commit)
    baseline_ref.harness_path = relative_to_root(root, baseline_file)
    candidate_ref.harness_path = relative_to_root(root, candidate_file)

    return evaluate(
        dataset=load_dataset(dataset_path),
        baseline=baseline,
        baseline_ref=baseline_ref,
        candidate=candidate,
        candidate_ref=candidate_ref,
        gates=load_gates(gates_path),
        pricing=load_pricing(pricing_path),
        project=config.project,
        trials=config.trials if trials is None else trials,
        seed=config.seed if seed is None else seed,
        case_timeout_s=config.case_timeout_s,
        dataset_path=relative_to_root(root, dataset_path),
    )


def replay_project(
    report: EvaluationReport,
    root: Optional[Path] = None,
    config_path: Optional[Path] = None,
) -> EvaluationReport:
    root = (root or find_repo_root()).resolve()
    config_file = config_path or (root / ".agentgate" / "config.yaml")
    config = load_project_config(config_file)
    return replay_report(
        report,
        root,
        resolve_inside(root, config.gates),
        resolve_inside(root, config.pricing),
    )
