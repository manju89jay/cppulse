import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { HealthScore } from "../HealthScore";
import type { HealthScore as HealthScoreType } from "../../types";

const healthyScore: HealthScoreType = {
  overall: 85.6,
  memory_safety: 90,
  modernization: 80,
  complexity: 75,
  misra_compliance: 88,
};

const criticalScore: HealthScoreType = {
  overall: 25,
  memory_safety: 10,
  modernization: 30,
  complexity: 20,
  misra_compliance: 35,
};

const middleScore: HealthScoreType = {
  overall: 55,
  memory_safety: 50,
  modernization: 60,
  complexity: 45,
  misra_compliance: 55,
};

describe("HealthScore", () => {
  it("renders the overall score rounded", () => {
    render(<HealthScore healthScore={healthyScore} />);
    expect(screen.getByText("86")).toBeInTheDocument();
  });

  it("shows 'Healthy' label for scores above 70", () => {
    render(<HealthScore healthScore={healthyScore} />);
    expect(screen.getByText("Healthy")).toBeInTheDocument();
  });

  it("shows 'Critical' label for scores below 40", () => {
    render(<HealthScore healthScore={criticalScore} />);
    expect(screen.getByText("Critical")).toBeInTheDocument();
  });

  it("shows 'Needs Attention' label for scores between 40-70", () => {
    render(<HealthScore healthScore={middleScore} />);
    expect(screen.getByText("Needs Attention")).toBeInTheDocument();
  });

  it("renders all four category score cards", () => {
    render(<HealthScore healthScore={healthyScore} />);
    expect(screen.getByText("Memory Safety")).toBeInTheDocument();
    expect(screen.getByText("Modernization")).toBeInTheDocument();
    expect(screen.getByText("Complexity finding health")).toBeInTheDocument();
    expect(screen.getByText("MISRA subset")).toBeInTheDocument();
  });

  it("renders the heading", () => {
    render(<HealthScore healthScore={healthyScore} />);
    expect(screen.getByText("Health Score")).toBeInTheDocument();
  });
});

 it("does not score missing input", () => { render(<HealthScore healthScore={{overall: null} as any} />); expect(screen.getByText(/No score/)).toBeInTheDocument(); });

it("distinguishes partial analysis from no input and retains its limitations", () => {
  const partial = {
    ...healthyScore,
    overall: null,
    status: "partial" as const,
    limitations: ["src/partial.cpp could not be fully analyzed."],
  };
  render(<HealthScore healthScore={partial} />);
  expect(screen.getByText(/analysis is incomplete/i)).toBeInTheDocument();
  expect(screen.getByText(partial.limitations[0])).toBeInTheDocument();
  expect(screen.queryByText(/no input files/i)).not.toBeInTheDocument();
  expect(screen.queryByText("Healthy")).not.toBeInTheDocument();
});

it("shows genuine empty-input status separately", () => {
  const empty = { ...healthyScore, overall: null, status: "no_data" as const };
  render(<HealthScore healthScore={empty} />);
  expect(screen.getByText(/no input files were assessed/i)).toBeInTheDocument();
});

it("shows available-result limitations beside a numeric score", () => {
  const scored = { ...healthyScore, status: "scored" as const, limitations: ["Git history is unavailable."] };
  render(<HealthScore healthScore={scored} />);
  expect(screen.getByText("86")).toBeInTheDocument();
  expect(screen.getByText(scored.limitations[0])).toBeInTheDocument();
});
