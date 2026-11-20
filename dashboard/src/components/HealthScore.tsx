import React from "react";
import type { HealthScore as HealthScoreType } from "../types";

interface HealthScoreProps {
  healthScore: HealthScoreType;
}

function getScoreColor(score: number): string {
  if (score > 70) return "text-green-600";
  if (score >= 40) return "text-amber-500";
  return "text-red-600";
}

function getScoreBg(score: number): string {
  if (score > 70) return "bg-green-100 border-green-300";
  if (score >= 40) return "bg-amber-100 border-amber-300";
  return "bg-red-100 border-red-300";
}

function getScoreLabel(score: number): string {
  if (score > 70) return "Healthy";
  if (score >= 40) return "Needs Attention";
  return "Critical";
}

interface ScoreCardProps {
  label: string;
  score: number | null | undefined;
}

function ScoreCard({ label, score }: ScoreCardProps): React.ReactElement {
  const available = typeof score === "number";
  const rounded = available ? Math.round(score) : "N/A";
  return (
    <div className={`border rounded-lg p-4 ${available ? getScoreBg(score) : "bg-gray-50 border-gray-200"}`}>
      <p className="text-sm text-gray-600 font-medium">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${available ? getScoreColor(score) : "text-gray-500"}`}>
        {rounded}
      </p>
    </div>
  );
}

export function HealthScore({
  healthScore,
}: HealthScoreProps): React.ReactElement {
  const limitations = healthScore.limitations ?? [];
  const limitationNotes = limitations.length > 0 && (
    <div className="mt-4 text-sm text-amber-800" role="note">
      <p className="font-semibold">Analysis limitations</p>
      <ul className="list-disc pl-5 mt-1">
        {limitations.map((message, index) => <li key={index}>{message}</li>)}
      </ul>
    </div>
  );
  if (healthScore.overall === null || healthScore.status === "partial") {
    const explanation = healthScore.status === "partial"
      ? "No score: analysis is incomplete. Findings from analyzed files remain available."
      : healthScore.status === "no_data"
        ? "No score: no input files were assessed."
        : "No score available for this analysis.";
    return (
      <div className="bg-white rounded-xl shadow p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Health Score</h2>
        <p>{explanation}</p>
        {limitationNotes}
      </div>
    );
  }
  const overall = Math.round(healthScore.overall);
  return (
    <div className="bg-white rounded-xl shadow p-6">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">
        Health Score
      </h2>
      <div className="flex items-center gap-6">
        {/* Big circular score */}
        <div
          className={`w-28 h-28 rounded-full border-4 flex flex-col items-center justify-center shadow-inner ${getScoreBg(healthScore.overall)}`}
        >
          <span
            className={`text-4xl font-extrabold ${getScoreColor(healthScore.overall)}`}
          >
            {overall}
          </span>
          <span className="text-xs text-gray-500 mt-1">/ 100</span>
        </div>
        <div>
          <p
            className={`text-xl font-bold ${getScoreColor(healthScore.overall)}`}
          >
            {getScoreLabel(healthScore.overall)}
          </p>
          <p className="text-sm text-gray-500 mt-1">Overall codebase health</p>
        </div>
      </div>

      {/* Category breakdown */}
      <div className="grid grid-cols-2 gap-3 mt-5">
        <ScoreCard label="Memory Safety" score={healthScore.memory_safety} />
        <ScoreCard label="Modernization" score={healthScore.modernization} />
        <ScoreCard label="Complexity finding health" score={healthScore.complexity} />
        {healthScore.misra_compliance !== undefined && <ScoreCard label="MISRA subset" score={healthScore.misra_compliance} />}
      </div>
      <p className="mt-3 text-sm text-gray-500">Category health uses finding density. Measured cyclomatic complexity is reported separately in hotspots.</p>
      {limitationNotes}
    </div>
  );
}
