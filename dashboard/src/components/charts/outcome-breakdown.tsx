import { useMemo } from "react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from "recharts";

interface OutcomeBreakdownProps {
  outcomes: {
    success: number;
    failure: number;
    partial: number;
  };
}

const OUTCOME_CONFIG = [
  { key: "success", label: "Success", color: "#10b981" },
  { key: "failure", label: "Failure", color: "#f43f5e" },
  { key: "partial", label: "Partial", color: "#f59e0b" },
] as const;

export function OutcomeBreakdown({ outcomes }: OutcomeBreakdownProps) {
  const data = useMemo(
    () =>
      OUTCOME_CONFIG.map(({ key, label, color }) => ({
        name: label,
        value: outcomes[key],
        color,
      })).filter((d) => d.value > 0),
    [outcomes],
  );

  const total = outcomes.success + outcomes.failure + outcomes.partial;

  if (total === 0) {
    return (
      <div className="flex h-[200px] items-center justify-center text-sm text-zinc-500">
        No outcome data
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={200}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={50}
          outerRadius={75}
          paddingAngle={2}
          dataKey="value"
          strokeWidth={0}
        >
          {data.map((entry) => (
            <Cell key={entry.name} fill={entry.color} fillOpacity={0.8} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            backgroundColor: "#18181b",
            border: "1px solid #3f3f46",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelStyle={{ color: "#e4e4e7" }}
        />
        <Legend
          verticalAlign="bottom"
          height={28}
          formatter={(value: string) => (
            <span className="text-xs text-zinc-400">{value}</span>
          )}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
