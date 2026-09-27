"""Failure classes.

Agent behavior, provider outages, and local infrastructure problems are
different events. Callers must not collapse them into a single score.
"""

from __future__ import annotations


class AgentGateError(Exception):
    """Base error for expected, user-facing failures."""


class ConfigError(AgentGateError):
    """The evaluation configuration is invalid."""


class ReplayError(AgentGateError):
    """A replay refused to run because an input drifted."""


class ProviderError(AgentGateError):
    """The model provider failed. This is not an agent behavior failure."""


class InfrastructureError(AgentGateError):
    """Local infrastructure failed. This is not an agent behavior failure."""
