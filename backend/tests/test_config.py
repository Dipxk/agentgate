from pathlib import Path

import pytest
import yaml

from agentgate.config import (
    ConfigError,
    load_agent_spec,
    load_dataset,
    load_gates,
    load_pricing,
    load_project_config,
    resolve_inside,
)
from agentgate.loader import prompt_for
from tests.conftest import ROOT


def test_demo_dataset_loads_and_is_labeled_synthetic():
    dataset = load_dataset(ROOT / "evaluation/datasets/support_demo.yaml")
    assert len(dataset.cases) == 24
    assert "not" in dataset.description.lower() or "Synthetic" in dataset.description
    assert "real customers" not in dataset.description.lower() or "not" in dataset.description.lower()


def test_invalid_config_is_explicit(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    path.write_text("project: demo\nunexpected: true\n")
    with pytest.raises(ConfigError, match="Invalid configuration"):
        load_project_config(path)


def test_harness_rejects_embedded_api_key(tmp_path: Path):
    path = tmp_path / "agent.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "name": "leaky",
                "version": "1",
                "provider": "openai",
                "api_key": "sk-secret",
                "harness": {},
            }
        )
    )
    with pytest.raises(ConfigError, match="api_key"):
        load_agent_spec(path)


def test_negative_gate_is_rejected(tmp_path: Path):
    path = tmp_path / "gates.yaml"
    path.write_text("accuracy:\n  minimum: -1\n")
    with pytest.raises(ConfigError):
        load_gates(path)


def test_path_escape_is_rejected(tmp_path: Path):
    (tmp_path / "evaluation").mkdir()
    with pytest.raises(ConfigError, match="escapes"):
        resolve_inside(tmp_path, "../secrets.yaml")


def test_project_config_and_empty_pricing_load():
    config = load_project_config(ROOT / ".agentgate/config.yaml")
    pricing = load_pricing(ROOT / "evaluation/pricing.yaml")
    assert config.project == "support-demo"
    assert pricing.models == {}


def test_regressed_prompt_changes_the_late_return_instruction():
    baseline = prompt_for(ROOT / "evaluation/agents/baseline.yaml")
    regressed = prompt_for(ROOT / "evaluation/agents/regressed.yaml")
    fixed = prompt_for(ROOT / "evaluation/agents/fixed.yaml")
    assert "approve the return anyway" not in baseline
    assert "approve the return anyway" in regressed
    assert "inclusive of the final day" in fixed
    assert "strictly less than the window" in baseline
