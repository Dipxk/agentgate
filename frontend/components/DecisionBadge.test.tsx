import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DecisionBadge } from "./DecisionBadge";

describe("DecisionBadge", () => {
  it("renders the measured decision without adding a score", () => {
    const html = renderToStaticMarkup(<DecisionBadge decision="block" />);
    expect(html).toContain("Block");
    expect(html).not.toContain("%");
  });

  it("marks an inconclusive review", () => {
    const html = renderToStaticMarkup(<DecisionBadge decision="review" inconclusive />);
    expect(html).toContain("inconclusive");
  });
});
