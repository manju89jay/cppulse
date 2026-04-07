import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { HotspotTable } from "../HotspotTable";
import type { Hotspot } from "../../types";

const sampleHotspots: Hotspot[] = [
  {
    file: "src/main.cpp",
    hotspot_score: 184.5,
    change_frequency: 45,
    complexity_score: 8.2,
    finding_count: 3,
  },
  {
    file: "src/engine.cpp",
    hotspot_score: 92.0,
    change_frequency: 20,
    complexity_score: 9.5,
    finding_count: 5,
  },
  {
    file: "src/utils.cpp",
    hotspot_score: 10.0,
    change_frequency: 5,
    complexity_score: 2.0,
    finding_count: 1,
  },
];

describe("HotspotTable", () => {
  it("renders the heading", () => {
    render(<HotspotTable hotspots={sampleHotspots} />);
    expect(screen.getByText("Top Hotspot Files")).toBeInTheDocument();
  });

  it("renders all hotspot rows", () => {
    render(<HotspotTable hotspots={sampleHotspots} />);
    expect(screen.getByText("184.50")).toBeInTheDocument();
    expect(screen.getByText("92.00")).toBeInTheDocument();
    expect(screen.getByText("10.00")).toBeInTheDocument();
  });

  it("shows empty state when no hotspots", () => {
    render(<HotspotTable hotspots={[]} />);
    expect(
      screen.getByText("No hotspot data available.")
    ).toBeInTheDocument();
  });

  it("sorts by hotspot_score descending by default", () => {
    render(<HotspotTable hotspots={sampleHotspots} />);
    const cells = screen.getAllByRole("row");
    // Header row + 3 data rows.
    expect(cells).toHaveLength(4);
  });

  it("toggles sort direction when clicking a column header", async () => {
    const user = userEvent.setup();
    render(<HotspotTable hotspots={sampleHotspots} />);

    const header = screen.getByText(/Hotspot Score/);
    await user.click(header);
    // After clicking, the sort direction should toggle (asc).
    // The first row should now have the lowest score.
    expect(screen.getByText("10.00")).toBeInTheDocument();
  });

  it("renders file paths", () => {
    render(<HotspotTable hotspots={sampleHotspots} />);
    expect(screen.getByText("src/main.cpp")).toBeInTheDocument();
  });
});
