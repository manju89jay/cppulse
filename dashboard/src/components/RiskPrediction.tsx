import React from "react";
import type { FileRisk, RankingScope, UnrankedFile } from "../types";

interface RiskPredictionProps {
  fileRisks: FileRisk[];
  unrankedFiles?: UnrankedFile[];
  rankingScope?: RankingScope | null;
}

function riskBadge(level: FileRisk["risk_level"]): React.ReactElement {
  const classes: Record<FileRisk["risk_level"], string> = {
    critical: "bg-red-100 text-red-700 border border-red-200",
    high: "bg-orange-100 text-orange-700 border border-orange-200",
    medium: "bg-yellow-100 text-yellow-700 border border-yellow-200",
    low: "bg-green-100 text-green-700 border border-green-200",
  };
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wide ${classes[level]}`}
    >
      {level}
    </span>
  );
}

function shortPath(path: string): string {
  const parts = path.split("/");
  if (parts.length <= 3) return path;
  return `.../${parts.slice(-2).join("/")}`;
}

export function RiskPrediction({
  fileRisks,
  unrankedFiles = [],
  rankingScope,
}: RiskPredictionProps): React.ReactElement {
  const topRisks = [...fileRisks]
    .sort((a, b) => b.bug_probability - a.bug_probability)
    .slice(0, 10);

  return (
    <div className="bg-white rounded-xl shadow p-6">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">
        Risk Prediction{" "}
        <span className="text-sm font-normal text-gray-500">
          (top 10 files)
        </span>
      </h2>
      <p className="text-sm text-gray-600 mb-4">Experimental prioritization scores are uncalibrated and do not measure the probability of a future defect.</p>
      {rankingScope && <p className="text-sm mb-4">Declared files: {rankingScope.declared_files}; ranked: {rankingScope.ranked_files}; without a usable rank: {rankingScope.unranked_files}.</p>}

      {topRisks.length === 0 ? (
        <p className="text-gray-400 text-sm">{unrankedFiles.length > 0 ? "No files have a usable rank." : "No risk data available."}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  File
                </th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  Experimental score
                </th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  Risk Level
                </th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  Top Factors
                </th>
              </tr>
            </thead>
            <tbody>
              {topRisks.map((risk, i) => (
                <tr
                  key={risk.file}
                  className={i % 2 === 0 ? "bg-white" : "bg-gray-50"}
                >
                  <td
                    className="px-3 py-2 text-sm text-gray-700"
                    title={risk.file}
                  >
                    <span className="font-mono text-xs">
                      {shortPath(risk.file)}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-sm">
                    <div className="flex items-center gap-2">
                      <div className="w-16 bg-gray-200 rounded-full h-1.5">
                        <div
                          className="bg-red-500 h-1.5 rounded-full"
                          style={{
                            width: `${Math.round(risk.bug_probability * 100)}%`,
                          }}
                        />
                      </div>
                      <span className="text-gray-700 font-semibold">
                        {Math.round(risk.bug_probability * 100)}%
                      </span>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-sm">
                    {riskBadge(risk.risk_level)}
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-500">
                    {risk.top_factors.slice(0, 3).join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {unrankedFiles.length > 0 && <section className="mt-6">
        <h3 className="font-semibold">Files without a usable rank ({unrankedFiles.length})</h3>
        <p className="text-sm text-gray-600 my-2">Showing {Math.min(50, unrankedFiles.length)} of {unrankedFiles.length} unavailable files. These files receive no numeric score or low-risk label; complete records remain in the original JSON.</p>
        <div className="space-y-3">{unrankedFiles.slice(0, 50).map(item => <article key={item.file} className="border border-amber-200 bg-amber-50 rounded p-3 text-sm">
          <p className="font-mono break-all">{item.file}</p><p>Availability: {item.availability}</p>
          <p className="text-xs text-gray-600">{item.reason_codes.join(", ")}</p>
          <ul>{item.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
        </article>)}</div>
      </section>}
    </div>
  );
}
