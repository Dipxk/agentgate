"""Construct runnable agents and version records from harness files."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from agentgate.agent import (
    AgentSpec,
    LLMSupportAgent,
    SupportAgent,
    build_system_prompt,
)
from agentgate.catalog import canonical_hash
from agentgate.config import load_agent_spec
from agentgate.domain import VersionRef
from agentgate.errors import ConfigError
from agentgate.providers import AnthropicProvider, OpenAIProvider


def spec_hash(spec: AgentSpec) -> str:
    return canonical_hash(spec.model_dump(mode="json"))


def provider_class_for(provider: str) -> str:
    if provider == "policy":
        return "deterministic_harness"
    if provider == "mock":
        return "development_double"
    return "model"


def build_agent(
    spec: AgentSpec,
    config_hash: str,
    harness_path: Optional[str] = None,
    commit: Optional[str] = None,
):
    if spec.agent != "support":
        raise ConfigError(f"Unknown agent type: {spec.agent}")
    if spec.provider == "policy":
        return SupportAgent(
            spec=spec,
            commit=commit,
            config_hash=config_hash,
            harness_path=harness_path,
        )
    if spec.provider == "openai":
        return LLMSupportAgent(
            spec=spec,
            provider=OpenAIProvider(),
            commit=commit,
            config_hash=config_hash,
            harness_path=harness_path,
        )
    if spec.provider == "anthropic":
        return LLMSupportAgent(
            spec=spec,
            provider=AnthropicProvider(),
            commit=commit,
            config_hash=config_hash,
            harness_path=harness_path,
        )
    if spec.provider == "mock":
        raise ConfigError(
            "MockProvider cannot be loaded from a harness file. "
            "It is a development double and is available only in tests."
        )
    raise ConfigError(f"Unknown provider: {spec.provider}")


def version_from_spec(
    spec: AgentSpec,
    path: Path,
    commit: Optional[str] = None,
) -> VersionRef:
    digest = spec_hash(spec)
    mode = "policy" if spec.provider == "policy" else "llm"
    return VersionRef(
        name=spec.name,
        version=spec.version,
        commit=commit,
        provider=spec.provider,
        provider_class=provider_class_for(spec.provider),  # type: ignore[arg-type]
        model=spec.model,
        config_hash=digest,
        harness_path=str(path),
        execution_mode=mode,  # type: ignore[arg-type]
    )


def load_version(path: Path, commit: Optional[str] = None):
    spec = load_agent_spec(path)
    ref = version_from_spec(spec, path, commit=commit)
    agent = build_agent(spec, ref.config_hash, harness_path=str(path), commit=commit)
    return spec, ref, agent


def prompt_for(path: Path) -> str:
    spec = load_agent_spec(path)
    return build_system_prompt(spec.harness)
