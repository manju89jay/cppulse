import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MeasuredFacts from "../MeasuredFacts";

describe("retained measured facts", () => {
  it("keeps null full-scope health unavailable beside observed context scores", () => {
    render(<MeasuredFacts kind="maintenance_health" document={{scorer: {id: "analyzed-kloc-context-v3"}, aggregate: {overall: null, status: "incomplete"}, contexts: [{job_context_id: "debug", overall: 100}], limitations: ["release context missing"]}}/>);
    expect(screen.getByText("Full-scope health: unavailable")).toBeInTheDocument();
    expect(screen.getByText(/release context missing/)).toBeInTheDocument();
    expect(screen.getByText(/debug/)).toBeInTheDocument();
    expect(screen.getByText(/analyzed-kloc-context-v3/)).toBeInTheDocument();
  });
  it("filters retained metric rows and preserves missing values and units", () => {
    render(<MeasuredFacts kind="analysis_metrics" document={{job_context_id: "debug", items: [
      {id: "one", file: "a/main.cpp", symbol: "function-a", metric: "cyclomatic_complexity", value: 7, units: "count", availability: "available"},
      {id: "two", file: "b/main.cpp", metric: "physical_loc", value: null, units: "lines", availability: "unavailable"},
    ]}}/>);
    expect(screen.getAllByText("unavailable")).toHaveLength(2);
    fireEvent.change(screen.getByRole("textbox", {name: "Filter measured file or symbol"}), {target: {value: "function-a"}});
    expect(screen.getByText("a/main.cpp")).toBeInTheDocument();
    expect(screen.queryByText("b/main.cpp")).not.toBeInTheDocument();
    expect(screen.getByText("7 count")).toBeInTheDocument();
  });
});

it("identifies stored v3 results without changing their values", () => {
  render(<MeasuredFacts kind="maintenance_health" document={{scorer:{id:"analyzed-kloc-context-v3"},aggregate:{overall:100},contexts:[]}}/>);
  expect(screen.getByText(/Historical v3 result/)).toBeInTheDocument();
  expect(screen.getByText("Full-scope health: 100")).toBeInTheDocument();
});

it("makes the v4 input prerequisite explicit beside a missing score", () => {
  render(<MeasuredFacts kind="maintenance_health" document={{scorer:{id:"analyzed-kloc-context-v4"},aggregate:{overall:null},contexts:[]}}/>);
  expect(screen.getByText(/Inferred parse opt-in does not waive/)).toBeInTheDocument();
  expect(screen.getByText("Full-scope health: unavailable")).toBeInTheDocument();
  expect(screen.queryByText(/Historical v3 result/)).not.toBeInTheDocument();
});
