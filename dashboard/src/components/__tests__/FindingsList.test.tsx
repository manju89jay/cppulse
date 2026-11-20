import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { FindingsList } from "../FindingsList";
import type { Finding } from "../../types";

const sampleFindings: Finding[] = [
  {
    id: "1",
    rule_id: "CPP-MEM-001",
    file: "src/main.cpp",
    line: 42,
    column: 5,
    severity: "error",
    category: "memory_safety",
    message: "Raw pointer detected",
    suggestion: "Use std::unique_ptr",
  },
  {
    id: "2",
    rule_id: "CPP-MOD-004",
    file: "src/utils.cpp",
    line: 10,
    column: 1,
    severity: "warning",
    category: "modernization",
    message: "Use nullptr instead of NULL",
    suggestion: "Replace NULL with nullptr",
  },
  {
    id: "3",
    rule_id: "CPP-CX-001",
    file: "src/engine.cpp",
    line: 100,
    column: 3,
    severity: "warning",
    category: "complexity",
    message: "High cyclomatic complexity",
    suggestion: "Decompose function",
  },
];

describe("FindingsList", () => {
  it("renders all findings by default", () => {
    render(<FindingsList findings={sampleFindings} />);
    expect(screen.getByText("Raw pointer detected")).toBeInTheDocument();
    expect(screen.getByText(/Use nullptr/)).toBeInTheDocument();
    expect(screen.getByText("High cyclomatic complexity")).toBeInTheDocument();
  });

  it("shows the total count", () => {
    render(<FindingsList findings={sampleFindings} />);
    expect(screen.getByText("(3)")).toBeInTheDocument();
  });

  it("renders severity badges", () => {
    render(<FindingsList findings={sampleFindings} />);
    expect(screen.getByText("error")).toBeInTheDocument();
    expect(screen.getAllByText("warning")).toHaveLength(2);
  });

  it("shows rule IDs", () => {
    render(<FindingsList findings={sampleFindings} />);
    expect(screen.getByText("CPP-MEM-001")).toBeInTheDocument();
    expect(screen.getByText("CPP-MOD-004")).toBeInTheDocument();
  });

  it("renders suggestions", () => {
    render(<FindingsList findings={sampleFindings} />);
    expect(screen.getByText(/Use std::unique_ptr/)).toBeInTheDocument();
  });

  it("filters by category when selected", async () => {
    const user = userEvent.setup();
    render(<FindingsList findings={sampleFindings} />);

    const select = screen.getByRole("combobox");
    await user.selectOptions(select, "memory_safety");

    expect(screen.getByText("Raw pointer detected")).toBeInTheDocument();
    expect(screen.queryByText(/Use nullptr/)).not.toBeInTheDocument();
    expect(screen.getByText("(1)")).toBeInTheDocument();
  });

  it("shows empty message when no findings match filter", async () => {
    const user = userEvent.setup();
    render(<FindingsList findings={sampleFindings} />);

    const select = screen.getByRole("combobox");
    await user.selectOptions(select, "misra");

    expect(
      screen.getByText("No findings for this category.")
    ).toBeInTheDocument();
  });

  it("renders empty state with no findings", () => {
    render(<FindingsList findings={[]} />);
    expect(
      screen.getByText("No findings for this category.")
    ).toBeInTheDocument();
  });
});
