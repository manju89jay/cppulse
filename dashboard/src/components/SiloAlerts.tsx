import React from "react";
import type { KnowledgeSilo } from "../types";

interface SiloAlertsProps {
  silos: KnowledgeSilo[];
}

function shortPath(path: string): string {
  const parts = path.split("/");
  if (parts.length <= 3) return path;
  return `.../${parts.slice(-2).join("/")}`;
}

export function SiloAlerts({ silos }: SiloAlertsProps): React.ReactElement {
  return (
    <div className="bg-white rounded-xl shadow p-6">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">
        Knowledge Silos{" "}
        <span className="text-sm font-normal text-gray-500">
          ({silos.length})
        </span>
      </h2>

      {silos.length === 0 ? (
        <p className="text-gray-400 text-sm">
          No knowledge silos detected. Good team coverage!
        </p>
      ) : (
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
                    &bull; {silo.commit_count} commits &bull; Last:{" "}
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
      )}
    </div>
  );
}
