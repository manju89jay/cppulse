import React, { useEffect, useState } from "react";
import { Layout } from "./components/Layout";
import { HealthScore } from "./components/HealthScore";
import { CategoryBreakdown } from "./components/CategoryBreakdown";
import { HotspotTable } from "./components/HotspotTable";
import { FindingsList } from "./components/FindingsList";
import { SiloAlerts } from "./components/SiloAlerts";
import { RiskPrediction } from "./components/RiskPrediction";
import { Roadmap } from "./components/Roadmap";
import {
  fetchSummary,
  fetchFindings,
  fetchHotspots,
  fetchRisks,
  fetchSilos,
  fetchRoadmap,
} from "./api/client";
import type {
  Summary,
  FindingsResponse,
  Hotspot,
  RiskScores,
  KnowledgeSilo,
  RoadmapItem,
} from "./types";

type NavSection =
  | "overview"
  | "findings"
  | "hotspots"
  | "silos"
  | "risks"
  | "roadmap";

interface ApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

function useApiData<T>(
  fetcher: () => Promise<T>
): ApiState<T> & { reload: () => void } {
  const [state, setState] = useState<ApiState<T>>({
    data: null,
    loading: true,
    error: null,
  });

  function load(): void {
    setState({ data: null, loading: true, error: null });
    fetcher()
      .then((data) => setState({ data, loading: false, error: null }))
      .catch((err: unknown) => {
        const message =
          err instanceof Error ? err.message : "Unknown error occurred";
        setState({ data: null, loading: false, error: message });
      });
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { ...state, reload: load };
}

function LoadingSpinner(): React.ReactElement {
  return (
    <div className="flex items-center justify-center h-32">
      <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
    </div>
  );
}

function ErrorCard({ message }: { message: string }): React.ReactElement {
  return (
    <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm">
      <span className="font-semibold">Error: </span>
      {message}
    </div>
  );
}

function SummaryBanner({ summary }: { summary: Summary }): React.ReactElement {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 mb-6">
      <div className="bg-white rounded-lg shadow p-4">
        <p className="text-xs text-gray-500 uppercase tracking-wide">
          Repository
        </p>
        <p
          className="text-sm font-semibold text-gray-800 truncate mt-1"
          title={summary.repository}
        >
          {summary.repository}
        </p>
      </div>
      <div className="bg-white rounded-lg shadow p-4">
        <p className="text-xs text-gray-500 uppercase tracking-wide">
          Total Findings
        </p>
        <p className="text-2xl font-bold text-gray-800 mt-1">
          {summary.total_findings}
        </p>
      </div>
      <div className="bg-white rounded-lg shadow p-4">
        <p className="text-xs text-gray-500 uppercase tracking-wide">
          Critical Files
        </p>
        <p className="text-2xl font-bold text-red-600 mt-1">
          {summary.critical_files}
        </p>
      </div>
      <div className="bg-white rounded-lg shadow p-4">
        <p className="text-xs text-gray-500 uppercase tracking-wide">
          Knowledge Silos
        </p>
        <p className="text-2xl font-bold text-amber-600 mt-1">
          {summary.knowledge_silos}
        </p>
      </div>
    </div>
  );
}

export default function App(): React.ReactElement {
  const [activeSection, setActiveSection] = useState<NavSection>("overview");

  const summary = useApiData<Summary>(fetchSummary);
  const findings = useApiData<FindingsResponse>(() => fetchFindings());
  const hotspots = useApiData<Hotspot[]>(fetchHotspots);
  const risks = useApiData<RiskScores>(fetchRisks);
  const silos = useApiData<KnowledgeSilo[]>(fetchSilos);
  const roadmap = useApiData<RoadmapItem[]>(fetchRoadmap);

  function renderOverview(): React.ReactElement {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Overview</h1>

        {summary.loading && <LoadingSpinner />}
        {summary.error && <ErrorCard message={summary.error} />}
        {summary.data && <SummaryBanner summary={summary.data} />}

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Health Score */}
          {risks.loading && <LoadingSpinner />}
          {risks.error && <ErrorCard message={risks.error} />}
          {risks.data && (
            <HealthScore healthScore={risks.data.health_score} />
          )}

          {/* Category Breakdown */}
          {risks.data && (
            <CategoryBreakdown healthScore={risks.data.health_score} />
          )}
        </div>
      </div>
    );
  }

  function renderFindings(): React.ReactElement {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Findings</h1>
        {findings.loading && <LoadingSpinner />}
        {findings.error && <ErrorCard message={findings.error} />}
        {findings.data && (
          <FindingsList findings={findings.data.findings} />
        )}
      </div>
    );
  }

  function renderHotspots(): React.ReactElement {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900 mb-6">
          Hotspot Files
        </h1>
        {hotspots.loading && <LoadingSpinner />}
        {hotspots.error && <ErrorCard message={hotspots.error} />}
        {hotspots.data && <HotspotTable hotspots={hotspots.data} />}
      </div>
    );
  }

  function renderSilos(): React.ReactElement {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900 mb-6">
          Knowledge Silos
        </h1>
        {silos.loading && <LoadingSpinner />}
        {silos.error && <ErrorCard message={silos.error} />}
        {silos.data && <SiloAlerts silos={silos.data} />}
      </div>
    );
  }

  function renderRisks(): React.ReactElement {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900 mb-6">
          Risk Prediction
        </h1>
        {risks.loading && <LoadingSpinner />}
        {risks.error && <ErrorCard message={risks.error} />}
        {risks.data && (
          <RiskPrediction fileRisks={risks.data.file_risks} />
        )}
      </div>
    );
  }

  function renderRoadmap(): React.ReactElement {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900 mb-6">
          Refactoring Roadmap
        </h1>
        {roadmap.loading && <LoadingSpinner />}
        {roadmap.error && <ErrorCard message={roadmap.error} />}
        {roadmap.data && <Roadmap items={roadmap.data} />}
      </div>
    );
  }

  function renderSection(): React.ReactElement {
    switch (activeSection) {
      case "overview":
        return renderOverview();
      case "findings":
        return renderFindings();
      case "hotspots":
        return renderHotspots();
      case "silos":
        return renderSilos();
      case "risks":
        return renderRisks();
      case "roadmap":
        return renderRoadmap();
    }
  }

  return (
    <Layout activeSection={activeSection} onNavigate={setActiveSection}>
      {renderSection()}
    </Layout>
  );
}
