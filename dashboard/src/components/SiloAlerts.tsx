import React from "react";
import type { GitHistoryStatus, KnowledgeSilo } from "../types";

interface SiloAlertsProps {
  silos: KnowledgeSilo[];
  historyStatus?: GitHistoryStatus;
  limitations?: string[];
}

function shortPath(path: string): string {
  const parts = path.split("/");
  if (parts.length <= 3) return path;
  return `.../${parts.slice(-2).join("/")}`;
}

export function SiloAlerts({ silos, historyStatus = "unverified", limitations = [] }: SiloAlertsProps): React.ReactElement {
  return (
    <div className="bg-white rounded-xl shadow p-6">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">
        Knowledge Silos{" "}
        <span className="text-sm font-normal text-gray-500">
          ({silos.length})
        </span>
      </h2>

      {historyStatus !== "available" && <div className="mb-4 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded p-3">
        <p>Insufficient history for a complete knowledge assessment ({historyStatus}). Observed alerts cover only retained history; an empty list does not establish absent knowledge risk.</p>
        {limitations.length > 0 && <ul className="list-disc ml-5 mt-2">{limitations.map((value, index) => <li key={index}>{value}</li>)}</ul>}
      </div>}
      {silos.length === 0 && historyStatus === "available" ? (
        <p className="text-gray-400 text-sm">
          No single-contributor alerts in the available history.
        </p>
      ) : silos.length > 0 ? (
        <div className="space-y-3">
          {silos.map((silo) => (
            <div
              key={silo.file}
              className="border border-amber-200 bg-amber-50 rounded-lg p-4"
            >
              <div className="flex items-start gap-3">
                <div className="flex-shrink-0 w-8 h-8 bg-amber-400 rounded-full flex items-center justify-center">
                  <span className="text-white text-xs font-bold">!</span>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-gray-800 font-mono truncate">
                    {shortPath(silo.file)}
                  </p>
                  <p className="text-xs text-gray-600 mt-0.5">
                    Sole contributor:{" "}
                    <span className="font-semibold text-amber-700">
                      {silo.sole_contributor}
                    </span>{" "}
                    &bull; Last:{" "}
                    {silo.last_commit}
                  </p>
                  {silo.risk_note && (
                    <p className="text-xs text-amber-700 mt-1 italic">
                      {silo.risk_note}
                    </p>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
