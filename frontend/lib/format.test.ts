import { describe, expect, it } from "vitest";
import { formatDelta, formatRatio, formatUsd, providerLabel } from "./format";
import type { Rule } from "./types";

function rule(partial: Partial<Rule>): Rule {
  return {
    metric: "accuracy",
    label: "Behavioral accuracy",
    status: "pass",
    baseline: null,
    candidate: null,
    delta: null,
    delta_percent: null,
    delta_kind: "points",
    unit: "ratio",
    detail: "",
    ...partial,
  };
}

describe("formatters", () => {
  it("does not invent a number for a missing measurement", () => {
    expect(formatRatio(null)).toBe("Not measured");
    expect(formatUsd(undefined)).toBe("Not measured");
    expect(formatDelta(rule({}))).toBe("n/a");
  });

  it("formats ratio deltas as percentage points", () => {
    expect(
      formatDelta(
        rule({
          baseline: 0.914,
          candidate: 0.942,
          delta: 0.028,
          delta_kind: "points",
        }),
      ),
    ).toBe("+2.8 pp");
  });

  it("leaves a relative change blank when the baseline is zero", () => {
    expect(
      formatDelta(
        rule({
          unit: "usd",
          delta_kind: "relative",
          baseline: 0,
          candidate: 0.02,
          delta: 0.02,
          delta_percent: null,
        }),
      ),
    ).toBe("n/a");
  });

  it("labels the development double", () => {
    expect(providerLabel("development_double")).toBe("Development double");
    expect(providerLabel("deterministic_harness")).toBe("Deterministic harness");
  });
});
