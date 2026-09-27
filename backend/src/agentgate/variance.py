"""Observed run-to-run variance.

This module does not compute confidence intervals or claim statistical
significance. A small number of trials is reported as insufficient.
"""

from __future__ import annotations

import statistics
from typing import Optional, Sequence

from agentgate.domain import VarianceReport

VARIANCE_NOTE = (
    "These figures describe the observed trials. They are not a confidence "
    "interval and are not a test of statistical significance."
)


def sample_variance(values: Sequence[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)


def summarize_trials(
    accuracies: Sequence[Optional[float]],
    min_trials: int,
) -> VarianceReport:
    observed = [value for value in accuracies if value is not None]
    trials = len(accuracies)
    variance = sample_variance(observed)
    # Values below 1e-12 are floating-point residue, not a measured spread.
    if variance is not None and abs(variance) < 1e-12:
        variance = 0.0
    return VarianceReport(
        trials=trials,
        min_trials=min_trials,
        sufficient=trials >= min_trials and len(observed) == trials,
        mean_accuracy=(sum(observed) / len(observed)) if observed else None,
        median_accuracy=statistics.median(observed) if observed else None,
        sample_variance=variance,
        note=VARIANCE_NOTE,
    )
