"""Replay a stored run with the same dataset, harness, and evaluator version."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from agentgate import EVALUATOR_VERSION
from agentgate.catalog import canonical_hash
from agentgate.config import load_dataset, load_gates, load_pricing, resolve_inside
from agentgate.domain import EvaluationReport
from agentgate.engine import evaluate
from agentgate.errors import ReplayError
from agentgate.loader import load_version


def replay_report(
    report: EvaluationReport,
    root: Path,
    gates_path: Path,
    pricing_path: Path,
    allow_evaluator_drift: bool = False,
) -> EvaluationReport:
    manifest = report.manifest
    if manifest.evaluator_version != EVALUATOR_VERSION and not allow_evaluator_drift:
        raise ReplayError(
            f"Evaluator version changed from {manifest.evaluator_version} to {EVALUATOR_VERSION}. "
            "Refusing to replay. Start a new evaluation if you intend to use the current evaluators."
        )
    if not manifest.dataset_path:
        raise ReplayError("This run has no dataset path, so it cannot be replayed from disk.")
    dataset_path = resolve_inside(root, manifest.dataset_path) if not Path(manifest.dataset_path).is_absolute() else Path(manifest.dataset_path)
    dataset = load_dataset(dataset_path)
    digest = canonical_hash(dataset.model_dump(mode="json"))
    if digest != manifest.dataset_hash:
        raise ReplayError(
            "Dataset hash does not match the original run. "
            f"stored={manifest.dataset_hash} current={digest}"
        )

    def _load(ref, label: str):
        if ref is None:
            return None, None
        if not ref.harness_path:
            raise ReplayError(f"The {label} version has no harness path.")
        path = Path(ref.harness_path)
        if not path.is_absolute():
            path = resolve_inside(root, ref.harness_path)
        spec, loaded_ref, agent = load_version(path, commit=ref.commit)
        if loaded_ref.config_hash != ref.config_hash:
            raise ReplayError(
                f"{label} harness hash changed. stored={ref.config_hash} current={loaded_ref.config_hash}"
            )
        loaded_ref.provider_class = ref.provider_class
        return loaded_ref, agent

    baseline_ref, baseline = _load(manifest.baseline, "Baseline")
    candidate_ref, candidate = _load(manifest.candidate, "Candidate")
    if candidate is None or candidate_ref is None:
        raise ReplayError("Candidate version is missing.")
    gates = load_gates(gates_path)
    pricing = load_pricing(pricing_path)
    return evaluate(
        dataset=dataset,
        candidate=candidate,
        candidate_ref=candidate_ref,
        baseline=baseline,
        baseline_ref=baseline_ref,
        gates=gates,
        pricing=pricing,
        project=manifest.project,
        trials=manifest.trials,
        seed=manifest.seed,
        dataset_path=manifest.dataset_path,
    )
