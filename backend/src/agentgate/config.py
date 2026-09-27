"""Load project, dataset, gate, and harness files."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agentgate.agent import AgentSpec
from agentgate.domain import Dataset
from agentgate.errors import ConfigError
from agentgate.gates import GateConfig
from agentgate.pricing import PricingTable


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: str
    dataset: str
    gates: str
    pricing: str
    baseline: str
    candidate: str
    trials: int = Field(default=1, ge=1, le=20)
    seed: int = 0
    case_timeout_s: float = Field(default=30, gt=0)
    dashboard_url: Optional[str] = None


def find_repo_root(start: Optional[Path] = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".agentgate").is_dir() or (candidate / "evaluation").is_dir():
            return candidate
    raise ConfigError("Could not find the AgentGate project root (missing .agentgate/ or evaluation/).")


def _read_yaml(path: Path) -> object:
    if not path.is_file():
        raise ConfigError(f"File not found: {path}")
    try:
        loaded = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
    if loaded is None:
        raise ConfigError(f"Empty YAML file: {path}")
    return loaded


def _parse(model, payload: object, path: Path):
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise ConfigError(f"Invalid configuration in {path}:\n{exc}") from exc


def load_project_config(path: Path) -> ProjectConfig:
    return _parse(ProjectConfig, _read_yaml(path), path)


def load_dataset(path: Path) -> Dataset:
    return _parse(Dataset, _read_yaml(path), path)


def load_gates(path: Path) -> GateConfig:
    return _parse(GateConfig, _read_yaml(path), path)


def load_pricing(path: Path) -> PricingTable:
    return _parse(PricingTable, _read_yaml(path), path)


def load_agent_spec(path: Path) -> AgentSpec:
    return _parse(AgentSpec, _read_yaml(path), path)


def resolve_inside(root: Path, relative: str) -> Path:
    """Resolve a project path and refuse to leave the repository root."""

    root = root.resolve()
    candidate = (root / relative).resolve()
    if root != candidate and root not in candidate.parents:
        raise ConfigError(f"Path escapes the project root: {relative}")
    return candidate
