import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { SiloAlerts } from "../SiloAlerts";
import type { KnowledgeSilo } from "../../types";

const sampleSilos: KnowledgeSilo[] = [
  {
    file: "src/utils.cpp",
    sole_contributor: "alice",
    commit_count: 42,
    last_commit: "2026-02-15",
    risk_note: "Only Alice has touched this file in 12 months",
  },
  {
    file: "src/very/deep/nested/parser.cpp",
    sole_contributor: "bob",
    commit_count: 10,
    last_commit: "2026-01-20",
    risk_note: "",
  },
];

describe("SiloAlerts", () => {
  it("renders the heading with count", () => {
    render(<SiloAlerts silos={sampleSilos} />);
    expect(screen.getByText("Knowledge Silos")).toBeInTheDocument();
    expect(screen.getByText("(2)")).toBeInTheDocument();
  });

  it("renders contributor names", () => {
    render(<SiloAlerts silos={sampleSilos} />);
    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.getByText("bob")).toBeInTheDocument();
  });

  it("renders risk notes when present", () => {
    render(<SiloAlerts silos={sampleSilos} />);
    expect(
      screen.getByText("Only Alice has touched this file in 12 months")
    ).toBeInTheDocument();
  });

  it("shows empty state when no silos", () => {
    render(<SiloAlerts silos={[]} />);
    expect(
      screen.getByText(/No knowledge silos detected/)
    ).toBeInTheDocument();
  });

  it("shortens deep paths", () => {
    render(<SiloAlerts silos={sampleSilos} />);
    expect(screen.getByText(".../nested/parser.cpp")).toBeInTheDocument();
  });
});
