import { it, expect, vi, afterEach } from "vitest";
import { fetchArtifact, fetchSnapshotReport, fetchSnapshotView, fetchFindings, fetchHotspots, fetchRisks, fetchRoadmap, fetchSilos, fetchSummary, legacySections } from "../client";
import type { SnapshotView } from "../../types";
afterEach(() => vi.unstubAllGlobals());
it("adapts actual API envelopes, nested scores and factor objects", async () => {
 const payloads: Record<string, unknown> = {
  summary: {health_score: {overall: 91, by_category: {memory_safety: 85}}, findings_summary: {total_findings: 1}, metadata: {repo_path: "/fixture", analyzed_at: "today"}},
  findings: {items: [{rule_id: "CPP-MEM-001", file: "a.cpp"}], total: 1, page: 1, per_page: 50},
  risks: {items: [{file: "a.cpp", risk_level: "critical", top_factors: [{feature: "churn_rate", importance: 1, value: 3}]}], total: 1},
  hotspots: {items: [{file: "a.cpp", hotspot_score: 2}], total: 1},
  silos: {items: [{file: "a.cpp", last_commit_date: "2026-11-13"}], total: 1},
  roadmap: {items: [{priority: 1, file: "a.cpp"}], total: 1}
 };
 vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ok: true, json: async () => payloads[url.split("/").pop()!.split("?")[0]]})));
 expect((await fetchSummary()).total_findings).toBe(1);
 expect((await fetchFindings()).findings[0].file).toBe("a.cpp");
 expect((await fetchHotspots())[0].hotspot_score).toBe(2);
 expect((await fetchRisks()).health_score.memory_safety).toBe(85);
 expect((await fetchRisks()).file_risks[0].top_factors).toEqual(["churn_rate"]);
 expect((await fetchSilos())[0].last_commit).toBe("2026-11-13");
 expect((await fetchRoadmap())[0].priority).toBe(1);
});

it("loads all finding pages when no individual page is requested", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ok: true, json: async () => ({
    items: [{file: (new URL(url, "http://localhost").searchParams.get("page") === "2") ? "second.cpp" : "first.cpp"}],
    total: 2, page: (new URL(url, "http://localhost").searchParams.get("page") === "2") ? 2 : 1, per_page: 1, total_pages: 2
  })})));
  const result = await fetchFindings();
  expect(result.findings.map(item => item.file)).toEqual(["first.cpp", "second.cpp"]);
  expect(result.total).toBe(2);
});

it("preserves partial status and producer limitations for dashboard health", async () => {
  const limitation = "1 file has incomplete static-analysis results.";
  const responses: Record<string, unknown> = {
    summary: {
      health_score: { overall: null, status: "partial", by_category: { memory_safety: null, overall: 100 } },
      findings_summary: { total_findings: 2 },
      metadata: { repo_path: "/partial", analyzed_at: "today" },
      model_metadata: { model_type: "heuristic", profile: "default", experimental: true, limitations: [limitation] },
    },
    risks: { items: [], total: 0 },
    silos: { items: [], total: 0 },
    hotspots: { items: [], total: 0 },
  };
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ok: true, json: async () => responses[url.split("/").pop()!]})));
  const summary = await fetchSummary();
  const risks = await fetchRisks();
  expect(summary.health_score).toMatchObject({ overall: null, status: "partial", limitations: [limitation] });
  expect(risks.health_score).toMatchObject({ overall: null, status: "partial", limitations: [limitation] });
});

it("pins view and raw/report downloads to both exact identities while preserving optional authorization", async () => {
  const value = {version:"2.0.0",run:{id:"selected-run",manifest_sha256:"a".repeat(64)},assessment:{artifact_id:"assessment:current"}} as unknown as SnapshotView;
  const fetcher = vi.fn(async (_url: string, _options?: RequestInit) => ({ok:true,json:async()=>value,blob:async()=>new Blob(["selected retained bytes"])}));
  vi.stubGlobal("fetch",fetcher);
  expect(await fetchSnapshotView({runId:value.run.id,manifestSha256:value.run.manifest_sha256,apiKey:"local-key"})).toBe(value);
  await fetchArtifact(value,"raw:log","local-key");
  await fetchSnapshotReport(value,"pdf","local-key");
  expect(fetcher.mock.calls).toHaveLength(3);
  for (const [url,options] of fetcher.mock.calls) {
    expect(url).toContain(`manifest_sha256=${value.run.manifest_sha256}`);
    expect(options?.headers).toEqual({Authorization:"Bearer local-key"});
    expect(options?.cache).toBe("no-store");
    expect(url).not.toContain("local-key");
  }
  expect(fetcher.mock.calls[1][0]).toContain("/runs/selected-run/artifacts/raw%3Alog?");
  expect(fetcher.mock.calls[2][0]).toContain("assessment_artifact_id=assessment%3Acurrent");
});

it("refuses a partial run selection before making any request", async () => {
  const fetcher=vi.fn();vi.stubGlobal("fetch",fetcher);
  await expect(fetchSnapshotView({runId:"selected-run"})).rejects.toThrow(/both/);
  expect(fetcher).not.toHaveBeenCalled();
});

it("preserves unavailable files through the risk API adapter", async () => {
  const unavailable = [{file:"src/incomplete.hpp",availability:"partial",reason_codes:["PARTIAL_ANALYSIS"],reasons:["Selected parse failed."]}];
  const payloads:Record<string, unknown> = {
    summary:{health_score:{overall:null,status:"partial",by_category:{}},findings_summary:{total_findings:0},metadata:{repo_path:"/fixture",analyzed_at:"today"}},
    risks:{items:[],total:0,unranked_files:unavailable,unranked_total:1},
    hotspots:{items:[],total:0},
  };
  vi.stubGlobal("fetch",vi.fn(async(url:string)=>({ok:true,json:async()=>payloads[url.split("/").pop()!]})));
  expect((await fetchRisks()).unranked_files).toEqual(unavailable);
});

it("keeps history availability separate from the observed silo count", () => {
  const result=legacySections({
    findings:{document:{metadata:{repo_path:"/fixture",analyzed_at:"today"},summary:{total_findings:0},findings:[]}},
    risk_scores:{document:{health_score:{overall:null,status:"partial",by_category:{}},file_risks:[],unranked_files:[{file:"incomplete.hpp",availability:"partial",reason_codes:["PARTIAL_ANALYSIS"],reasons:["Parse failed."]}],hotspots:[]}},
    git_metrics:{document:{metadata:{history_status:"partial",limitations:["Shallow history."]},knowledge_silos:[]}},roadmap:null,
  });
  expect(result.summary?.knowledge_silos).toBe(0);
  expect(result.summary?.knowledge_silos_status).toBe("partial");
  expect(result.historyStatus).toBe("partial");
  expect(result.historyLimitations).toEqual(["Shallow history."]);
  expect(result.risks?.unranked_files?.[0].file).toBe("incomplete.hpp");
});

it("retains hotspot method even when other legacy slots are missing", () => {
  const result = legacySections({findings:null, git_metrics:null, roadmap:null,
    risk_scores:{document:{metadata:{model_type:"heuristic",profile:"default",experimental:true,hotspot_method:"measured-cc-physical-kloc-v1"},health_score:{overall:null,status:"partial",by_category:{}},file_risks:[],hotspots:[]}}});
  expect(result.summary).toBeNull();
  expect(result.risks?.hotspot_method).toBe("measured-cc-physical-kloc-v1");
});
