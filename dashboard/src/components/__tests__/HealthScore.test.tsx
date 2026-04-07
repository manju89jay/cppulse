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
    expect(screen.getByText("Complexity")).toBeInTheDocument();
    expect(screen.getByText("MISRA Compliance")).toBeInTheDocument();
  });

  it("renders the heading", () => {
    render(<HealthScore healthScore={healthyScore} />);
    expect(screen.getByText("Health Score")).toBeInTheDocument();
  });
});
