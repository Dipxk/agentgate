"""Shared builders for pipeline tests."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from agentgate.domain import AgentResponse, Dataset, EvalCase, ExpectedBehavior, VersionRef
from agentgate.errors import InfrastructureError, ProviderError

ROOT = Path(__file__).resolve().parents[2]


def case(case_id: str, outcome: str = "ok", output: str = "ok") -> EvalCase:
    return EvalCase(
        id=case_id,
        input=case_id,
        expected_behavior=ExpectedBehavior(expected_outcome=outcome, expected_output=output),
    )


def dataset(*cases: EvalCase) -> Dataset:
    return Dataset(
        name="unit",
        version="1",
        description="Unit dataset. Not a benchmark.",
        cases=list(cases),
    )


class ScriptedAgent:
    provider = "policy"
    provider_class = "deterministic_harness"
    model = None
    execution_mode = "policy"

    def __init__(
        self,
        response: Optional[AgentResponse] = None,
        sleep_s: float = 0.0,
        error: Optional[Exception] = None,
        tokens: Optional[int] = None,
        model: Optional[str] = None,
    ) -> None:
        self.response = response
        self.sleep_s = sleep_s
        self.error = error
        self.tokens = tokens
        self.model = model
        if model:
            self.provider = "openai"
            self.provider_class = "model"
            self.execution_mode = "llm"

    def run(self, case_input: str) -> AgentResponse:
        if self.sleep_s:
            time.sleep(self.sleep_s)
        if self.error:
            raise self.error
        if self.response is not None:
            return self.response
        return AgentResponse(
            output="ok",
            outcome="ok",
            provider=self.provider,
            provider_class=self.provider_class,  # type: ignore[arg-type]
            model=self.model,
            input_tokens=self.tokens,
            output_tokens=self.tokens,
            needs_human_review=False,
        )


def ref(name: str = "candidate", provider_class: str = "deterministic_harness") -> VersionRef:
    return VersionRef(
        name=name,
        version="1",
        provider="policy" if provider_class != "model" else "openai",
        provider_class=provider_class,  # type: ignore[arg-type]
        model="example-model" if provider_class == "model" else None,
        config_hash="abc",
        execution_mode="policy" if provider_class != "model" else "llm",
    )


def infra_error() -> InfrastructureError:
    return InfrastructureError("Docker failed to start")


def provider_error() -> ProviderError:
    return ProviderError("API timeout")
