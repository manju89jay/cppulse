import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { RiskPrediction } from "../RiskPrediction";
import type { FileRisk } from "../../types";

const sampleRisks: FileRisk[] = [
  {
    file: "src/main.cpp",
    bug_probability: 0.82,
    risk_level: "critical",
    top_factors: ["change_frequency", "bug_fix_commits"],
  },
  {
    file: "src/utils.cpp",
    bug_probability: 0.4,
    risk_level: "medium",
    top_factors: ["churn_rate"],
  },
  {
    file: "src/safe.cpp",
    bug_probability: 0.1,
    risk_level: "low",
    top_factors: [],
  },
];

describe("RiskPrediction", () => {
  it("renders the heading", () => {
    render(<RiskPrediction fileRisks={sampleRisks} />);
    expect(screen.getByText("Risk Prediction")).toBeInTheDocument();
  });

  it("renders risk level badges", () => {
    render(<RiskPrediction fileRisks={sampleRisks} />);
    expect(screen.getByText("critical")).toBeInTheDocument();
    expect(screen.getByText("medium")).toBeInTheDocument();
    expect(screen.getByText("low")).toBeInTheDocument();
  });

  it("renders stored experimental scores as percentages", () => {
    render(<RiskPrediction fileRisks={sampleRisks} />);
    expect(screen.getByText("82%")).toBeInTheDocument();
    expect(screen.getByText("40%")).toBeInTheDocument();
    expect(screen.getByText("10%")).toBeInTheDocument();
  });

  it("renders top factors", () => {
    render(<RiskPrediction fileRisks={sampleRisks} />);
    expect(
      screen.getByText("change_frequency, bug_fix_commits")
    ).toBeInTheDocument();
  });

  it("shows empty state when no risks", () => {
    render(<RiskPrediction fileRisks={[]} />);
    expect(screen.getByText("No risk data available.")).toBeInTheDocument();
  });

  it("keeps unavailable files and their reasons visible without low-risk values", () => {
    render(<RiskPrediction fileRisks={[]} unrankedFiles={[{
      file: "src/incomplete.hpp", availability: "partial",
      reason_codes: ["PARTIAL_ANALYSIS"], reasons: ["A selected context failed to parse."],
    }]}/>);
    expect(screen.getByText("src/incomplete.hpp")).toBeInTheDocument();
    expect(screen.getByText("A selected context failed to parse.")).toBeInTheDocument();
    expect(screen.getByText("PARTIAL_ANALYSIS")).toBeInTheDocument();
    expect(screen.getByRole("heading", {name: /Files without a usable rank/})).toBeInTheDocument();
    expect(screen.queryByText("low")).not.toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });
});
