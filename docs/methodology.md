# Evaluation methodology

AgentGate compares a candidate agent with a baseline on the same dataset,
the same evaluators, and the same fixture catalog. A higher score on one
metric is not treated as a release by itself.

## What is scored

Behavioral accuracy is the fraction of agent-completed cases that passed
every applicable deterministic evaluator. Deterministic evaluators are:

- exact output match, when a case sets `expected_output`
- structured behavior: required tools, forbidden tools, tool order, expected
  outcome, and optional per-case latency or cost limits
- a dataset-authored code test, when one is set

Infrastructure errors and provider errors are excluded from the numerator
and the denominator. They are reported separately. They are not stored as an
accuracy of 0.

Tool-call success is the fraction of completed cases whose behavior
evaluator passed. It can differ from accuracy when another deterministic
evaluator fails.

Human-review rate is the fraction of completed cases the agent flagged for a
person. If the agent does not set the flag, the rate is not measured.

## Latency and cost

Request latency is the wall-clock time around the agent call, measured by
the engine. Model latency and tool latency are recorded when the runner
supplies them. Median and p95 use linear interpolation between the closest
ranks. They are descriptive. They are not confidence intervals.

A percent-increase rule is not applied when the baseline is below
`min_baseline_for_percent`. That avoids treating sub-millisecond noise in
the local harness as a regression. The absolute maximum still applies.

Cost is `input_tokens * input_price + output_tokens * output_price`, using
the pricing file. Prices are not embedded in the engine. If the provider
does not report tokens, or the model is absent from the pricing file, cost
is unavailable.

## Subjective judge

An optional LLM judge can score a rubric. Its result is stored as
subjective. A judge failure can move a decision from pass to review. It
cannot block a release, and it cannot pass one.

`MockProvider` is a scripted development double. A run that uses it cannot
pass a gate.

## Variance

When a run has multiple trials, AgentGate reports the mean, the median, and
the sample variance (divisor n − 1) of per-trial accuracy. Fewer than
`min_trials` trials is labeled insufficient. The project does not compute a
confidence interval and does not claim statistical significance.

## Replay

A replay refuses to run when the dataset hash, harness hash, or evaluator
version differs from the stored manifest. The seed and trial count are
reused. Wall-clock latency is measured again and is not required to match.
