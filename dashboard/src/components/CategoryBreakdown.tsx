import React from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import type { HealthScore } from "../types";

interface CategoryBreakdownProps {
  healthScore: HealthScore;
}

function getBarColor(value: number): string {
  if (value > 70) return "#16a34a";
  if (value >= 40) return "#d97706";
  return "#dc2626";
}

export function CategoryBreakdown({
  healthScore,
}: CategoryBreakdownProps): React.ReactElement {
  const data = [
    { name: "Memory Safety", score: Math.round(healthScore.memory_safety) },
    { name: "Modernization", score: Math.round(healthScore.modernization) },
    { name: "Complexity", score: Math.round(healthScore.complexity) },
    {
      name: "MISRA Compliance",
      score: Math.round(healthScore.misra_compliance),
    },
  ];

  return (
    <div className="bg-white rounded-xl shadow p-6">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">
        Category Scores
      </h2>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart
          data={data}
          margin={{ top: 5, right: 20, left: 0, bottom: 5 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis
            dataKey="name"
            tick={{ fontSize: 11 }}
            interval={0}
            angle={-15}
            textAnchor="end"
            height={45}
          />
          <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
          <Tooltip
            formatter={(value: number) => [`${value}`, "Score"]}
            contentStyle={{ fontSize: 12 }}
          />
          <Bar dataKey="score" radius={[4, 4, 0, 0]}>
            {data.map((entry, index) => (
              <Cell key={index} fill={getBarColor(entry.score)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
