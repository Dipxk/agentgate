import type { Rule } from "./types";

export function formatRatio(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "Not measured";
  return `${(value * 100).toFixed(1)}%`;
}

export function formatMs(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "Not measured";
  if (value < 1000) return `${value.toFixed(1)} ms`;
  return `${(value / 1000).toFixed(3)} s`;
}

export function formatUsd(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "Not measured";
  if (value === 0) return "$0";
  if (Math.abs(value) < 0.01) return `$${value.toFixed(6)}`;
  return `$${value.toFixed(4)}`;
}

export function formatMetric(rule: Pick<Rule, "unit">, value: number | null | undefined): string {
  if (rule.unit === "ratio") return formatRatio(value);
  if (rule.unit === "milliseconds") return formatMs(value);
  if (rule.unit === "usd") return formatUsd(value);
  if (value === null || value === undefined) return "Not measured";
  return String(value);
}

export function formatDelta(rule: Rule): string {
  if (rule.baseline === null || rule.candidate === null || rule.delta === null) return "n/a";
  if (rule.delta_kind === "relative") {
    if (rule.delta_percent === null) return "n/a";
    return `${signed(rule.delta_percent)}${rule.delta_percent.toFixed(1)}%`;
  }
  if (rule.unit === "ratio") {
    return `${signed(rule.delta * 100)}${(rule.delta * 100).toFixed(1)} pp`;
  }
  return `${signed(rule.delta)}${rule.delta.toPrecision(4)}`;
}

function signed(value: number): string {
  return value > 0 ? "+" : "";
}

export function providerLabel(providerClass: string): string {
  if (providerClass === "deterministic_harness") return "Deterministic harness";
  if (providerClass === "development_double") return "Development double";
  if (providerClass === "model") return "Model provider";
  return providerClass;
}

export function decisionLabel(decision: string, inconclusive = false): string {
  const name = decision === "pass" ? "Pass" : decision === "review" ? "Review" : decision === "block" ? "Block" : decision;
  return inconclusive ? `${name} · inconclusive` : name;
}
