import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";

// Synthetic UI transport data: these values are stored claims, not executed tools.
function snapshot(gate = "failed") {
  return {
    version: "2.0.0",
    run_manifest_json: '{"synthetic":"manifest bytes"}',
    run: {
      id: "selected-run", manifest_sha256: "a".repeat(64), status: "completed",
      input_verification: "unverified", source_digest: "b".repeat(64),
      inventory_complete: false, started_at: "2026-11-14T00:00:00Z",
      finished_at: "2026-11-14T00:01:00Z", config_digest: "c".repeat(64),
      limitations: ["Synthetic selected scope only."],
    },
    source: { digest: "b".repeat(64), kind: "application", files: [{ path: "main.cpp" }], inventory_complete: false },
    stages: [{ id: "actual-check", status: "failed", depends_on: [], reason: "Stored failure reason" }],
    contexts: [{ id: "gcc-job" }],
    assessment: {
      artifact_id: "assessment-original", sha256: "d".repeat(64), size_bytes: 100,
      raw_json: '{"synthetic":"original assessment bytes"}',
      display: {
        gate, run_id: "selected-run", source_digest: "b".repeat(64),
        policy: { id: "selected-policy", policy_version: "1.1.0", sha256: "e".repeat(64) },
        generated_at: "2026-11-14T00:01:00Z",
        weights: { passed: "9007199254740993", failed: "0", unknown: "0" },
        scores: { readiness: "100", evidence_completeness: "100", observed_satisfaction: "100", maximum_possible_readiness: "100" },
        controls: [{ id: "memory", title: "Stored memory check", status: "failed", reason: "Stored control reason", weight: "9007199254740993", required: true, evidence_ids: [], references: [] }],
        deviations: [], limitations: ["Stored assessment limitation."],
      },
    },
    facts: [{ kind: "sanitizer_facts", artifact_id: "sanitizer-original", sha256: "f".repeat(64), size_bytes: 50,
      raw_json: '{"synthetic":"sanitizer bytes"}', id: "sanitizer-selected", context_ids: ["gcc-job"],
      origin: "execution", producer: { name: "synthetic-ui-fixture", version: "1.0.0" },
      status: "findings", usability: "usable", limitations: ["Selected test only."] }],
    artifacts: [{ id: "sanitizer-original", path: "facts/sanitizer.json", sha256: "f".repeat(64), size_bytes: 50, media_type: "application/json" }],
    legacy: { findings: null, git_metrics: null, risk_scores: null, roadmap: null },
    gaps: [{ kind: "coverage", id: null, message: "No selected coverage facts.", artifact_ids: [] }],
    limitations: ["Synthetic selected scope only."],
  };
}

function mockView(value: unknown) {
  const fetcher = vi.fn(async (_url: string, _options?: RequestInit) => ({ ok: true, json: async () => value }));
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

afterEach(() => { vi.unstubAllGlobals(); window.history.replaceState({}, "", "/"); });

describe("one pinned dashboard snapshot", () => {
  it("shows the stored failed gate even when numeric display values look successful", async () => {
    const fetcher = mockView(snapshot("failed"));
    render(<App />);
    expect(await screen.findByRole("status", { name: "Stored policy gate" })).toHaveTextContent("failed");
    expect(screen.getAllByText("9007199254740993", { exact: true }).length).toBeGreaterThan(0);
    expect(screen.getByText("Stored control reason")).toBeInTheDocument();
    expect(screen.getByText("selected-run")).toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toBe("/api/v1/view");
  });

  it.each(["passed", "insufficient_evidence"])("displays stored %s without deriving a gate", async (gate) => {
    mockView(snapshot(gate));
    render(<App />);
    expect(await screen.findByRole("status", { name: "Stored policy gate" })).toHaveTextContent(gate);
  });

  it("keeps partial current facts visible with a missing assessment and no legacy fallback", async () => {
    const value = { ...snapshot(), assessment: null };
    value.run.status = "partial";
    mockView(value);
    render(<App />);
    expect(await screen.findByText("No stored assessment selected.")).toBeInTheDocument();
    expect(screen.getByText("partial", { exact: true })).toBeInTheDocument();
    expect(screen.getByText("Stored failure reason")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Evidence/ }));
    expect(screen.getByText("sanitizer-selected")).toBeInTheDocument();
    expect(screen.getByText("findings", { exact: true })).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "Stored policy gate" })).not.toBeInTheDocument();
  });

  it("clears the former snapshot when refresh fails instead of showing stale facts", async () => {
    const fetcher = mockView(snapshot("passed"));
    render(<App />);
    await screen.findByText("selected-run");
    fetcher.mockImplementationOnce(async () => { throw new Error("current unavailable"); });
    fireEvent.click(screen.getByRole("button", { name: "Refresh snapshot" }));
    expect(await screen.findByText(/current unavailable/)).toBeInTheDocument();
    expect(screen.queryByText("selected-run")).not.toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "Stored policy gate" })).not.toBeInTheDocument();
  });

  it("never lets a delayed old response replace a newer refresh", async () => {
    let completeOld: (value: unknown) => void = () => undefined;
    const old = new Promise((resolve) => { completeOld = resolve; });
    const fresh = snapshot("passed");
    fresh.run.id = "new-current-run";
    const fetcher = vi.fn().mockImplementationOnce(() => old)
      .mockResolvedValue({ ok: true, json: async () => fresh });
    vi.stubGlobal("fetch", fetcher);
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Refresh snapshot" }));
    await screen.findByText("new-current-run");
    await act(async () => { completeOld({ ok: true, json: async () => snapshot("failed") }); });
    await waitFor(() => expect(screen.queryByText("selected-run")).not.toBeInTheDocument());
    expect(screen.getByRole("status", { name: "Stored policy gate" })).toHaveTextContent("passed");
  });

  it("labels flat compatibility data explicitly without a stored policy gate", async () => {
    mockView({ mode: "legacy-flat", input_verification: "unverified",
      legacy: { findings: null, git_metrics: null, risk_scores: null, roadmap: null },
      limitations: ["Flat data has no immutable snapshot pin."] });
    render(<App />);
    expect(await screen.findByText(/Legacy flat compatibility/)).toBeInTheDocument();
    expect(screen.getByText("Flat data has no immutable snapshot pin.")).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "Stored policy gate" })).not.toBeInTheDocument();
  });

  it("retains unavailable ranks and history gaps while navigating one legacy view", async () => {
    mockView({mode:"legacy-flat",input_verification:"unverified",limitations:[],legacy:{
      findings:{document:{metadata:{repo_path:"/synthetic",analyzed_at:"today"},summary:{total_findings:0},findings:[]}},
      git_metrics:{document:{metadata:{history_status:"partial",limitations:["Shallow history."]},knowledge_silos:[]}},
      risk_scores:{document:{metadata:{model_type:"heuristic",profile:"default",experimental:true},health_score:{overall:null,status:"partial",by_category:{}},file_risks:[],unranked_files:[{file:"src/incomplete.hpp",availability:"partial",reason_codes:["PARTIAL_ANALYSIS"],reasons:["Selected parse failed."]}],hotspots:[]}},
      roadmap:null,
    }});
    render(<App/>);
    await screen.findByText(/Legacy flat compatibility/);
    const knowledgeCard=screen.getByText("Knowledge silos").parentElement!;
    expect(within(knowledgeCard).getByText("Unavailable")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button",{name:/Knowledge Silos/}));
    expect(screen.getByText(/Insufficient history/)).toBeInTheDocument();
    expect(screen.getByText("Shallow history.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button",{name:/Risk Prediction/}));
    expect(screen.getByText("src/incomplete.hpp")).toBeInTheDocument();
    expect(screen.getByText("Selected parse failed.")).toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
    expect(screen.queryByText("low")).not.toBeInTheDocument();
  });

  it("shows typed per-job observations without legacy findings and preserves exact line tokens", async () => {
    const value = snapshot();
    value.facts = [{ ...value.facts[0], kind: "observations", id: "job-findings", raw_json: '{"items":[{"id":"first","file":"main.cpp","line":9007199254740993,"rule_id":"CPP-MEM-001","severity":"warning","message":"Stored allocation finding","context_id":"job-a"},{"id":"second","file":"main.cpp","line":9007199254740993,"rule_id":"CPP-MEM-001","severity":"warning","message":"Stored allocation finding","context_id":"job-b"}]}' }];
    const fetcher = mockView(value);
    render(<App/>);
    await screen.findByText("selected-run");
    fireEvent.click(screen.getByRole("button", {name: "Findings"}));
    expect(screen.getAllByText("Stored allocation finding")).toHaveLength(2);
    expect(screen.getAllByText("main.cpp:9007199254740993")).toHaveLength(2);
    expect(screen.getByText(/Job: job-a/)).toBeInTheDocument();
    expect(screen.getByText(/Job: job-b/)).toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("shows consumer local-test gaps separately from compatibility and exact coverage/SAN facts", async () => {
    const value = snapshot();
    const original = value.facts[0];
    value.facts = [
      {...original,kind:"consumer_comparison",artifact_id:"comparison",raw_json:'{"import_origin":"import","authentication":"unverified","upstream_source_digest":"foreign","local_source_digest":"local","cases":[{"case_id":"application","status":"compatible","reason":"Stored configuration match","mismatches":[],"local_test_status":"unknown","missing_local_checks":["workload-test"]}]}'},
      {...original,kind:"coverage_facts",artifact_id:"coverage",raw_json:'{"files":[{"file":"main.cpp","measurements":[{"kind":"line","method":"gcov-lines","covered":9007199254740993,"total":9007199254740994}]}]}'},
      {...original,kind:"sanitizer_facts",artifact_id:"sanitizer",raw_json:'{"sanitizer":"ubsan","outcome":"failed","requested_files":["main.cpp"],"diagnostics":[{"kind":"signed-overflow","message":"Stored overflow diagnostic","file":"main.cpp","line":7}]}'},
    ];
    mockView(value); render(<App/>); await screen.findByText("selected-run");
    fireEvent.click(screen.getByRole("button",{name:"Evidence"}));
    expect(screen.getByText("compatible",{exact:true})).toBeInTheDocument();
    expect(screen.getByText(/Missing local checks: workload-test/)).toBeInTheDocument();
    expect(screen.getByText(/authentication: unverified/)).toBeInTheDocument();
    expect(screen.getByText("9007199254740993 / 9007199254740994")).toBeInTheDocument();
    expect(screen.getByText(/Stored overflow diagnostic/, {selector:"p"})).toBeInTheDocument();
  });

  it("joins the native inventory job and keeps imported compiler namespaces separate", async () => {
    const value=snapshot();const original=value.facts[0];
    value.facts=[
      {...original,kind:"analysis_inventory",artifact_id:"inventory",raw_json:'{"id":"inventory-one","job_context_id":"build-main"}'},
      {...original,kind:"observations",artifact_id:"native",raw_json:'{"analysis_inventory_id":"inventory-one","items":[{"id":"native-one","context_id":"parse-header","file":"include.hpp","line":3,"rule_id":"CPP-MEM-001","severity":"warning","message":"Native finding"}]}'},
      {...original,kind:"external_analysis_facts",artifact_id:"external",raw_json:'{"producer_namespace":"compiler.gcc","context_id":"external-job","observations":[{"id":"gcc-one","file":"main.cpp","line":4,"namespaced_rule_id":"compiler.gcc:unused","severity":"warning","message":"Imported compiler warning"}]}'},
    ];
    mockView(value);render(<App/>);await screen.findByText("selected-run");
    fireEvent.click(screen.getByRole("button",{name:"Findings"}));
    expect(screen.getByText(/Job: build-main; observation context: parse-header/)).toBeInTheDocument();
    expect(screen.getByText(/External analysis · compiler.gcc/)).toBeInTheDocument();
    expect(screen.getByText(/compiler.gcc:unused · warning/)).toBeInTheDocument();
    expect(screen.getByText("Imported compiler warning",{exact:true})).toBeInTheDocument();
  });
});
