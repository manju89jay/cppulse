import React from "react";
import type { RoadmapItem } from "../types";

interface RoadmapProps {
  items: RoadmapItem[];
}

function priorityBadge(priority: number): React.ReactElement {
  const color =
    priority === 1
      ? "bg-red-100 text-red-700 border border-red-200"
      : priority === 2
        ? "bg-orange-100 text-orange-700 border border-orange-200"
        : priority === 3
          ? "bg-yellow-100 text-yellow-700 border border-yellow-200"
          : "bg-gray-100 text-gray-600 border border-gray-200";
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${color}`}
    >
      P{priority}
    </span>
  );
}

function shortPath(path: string): string {
  const parts = path.split("/");
  if (parts.length <= 3) return path;
  return `.../${parts.slice(-2).join("/")}`;
}

export function Roadmap({ items }: RoadmapProps): React.ReactElement {
  const sorted = [...items].sort((a, b) => a.priority - b.priority);

  return (
    <div className="bg-white rounded-xl shadow p-6">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">
        Refactoring Roadmap{" "}
        <span className="text-sm font-normal text-gray-500">
          ({items.length} items)
        </span>
      </h2>

      {sorted.length === 0 ? (
        <p className="text-gray-400 text-sm">No roadmap items available.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  Priority
                </th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  File
                </th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  Action
                </th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  Category
                </th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  Est. Hours
                </th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  Impact
                </th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((item, i) => (
                <tr
                  key={`${item.file}-${item.priority}`}
                  className={i % 2 === 0 ? "bg-white" : "bg-gray-50"}
                >
                  <td className="px-3 py-2 text-sm">
                    {priorityBadge(item.priority)}
                  </td>
                  <td
                    className="px-3 py-2 text-sm text-gray-700"
                    title={item.file}
                  >
                    <span className="font-mono text-xs">
                      {shortPath(item.file)}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-sm text-gray-700 max-w-xs">
                    <span className="line-clamp-2">{item.action}</span>
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-500">
                    {item.category}
                  </td>
                  <td className="px-3 py-2 text-sm text-gray-700 text-right">
                    {item.estimated_hours}h
                  </td>
                  <td className="px-3 py-2 text-sm">
                    <div className="flex items-center gap-1">
                      <div className="w-12 bg-gray-200 rounded-full h-1.5">
                        <div
                          className="bg-blue-500 h-1.5 rounded-full"
                          style={{
                            width: `${Math.min(100, Math.round(item.impact_score))}%`,
                          }}
                        />
                      </div>
                      <span className="text-xs text-gray-600">
                        {item.impact_score.toFixed(1)}
                      </span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
