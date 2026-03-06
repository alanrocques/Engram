import { useMemo } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  ResponsiveContainer,
} from "recharts";
import type { Lesson } from "@/types/api";

interface UtilityDistributionProps {
  lessons: Lesson[];
}

function binColor(binStart: number): string {
  if (binStart < 0.3) return "#f43f5e";
  if (binStart < 0.7) return "#f59e0b";
  return "#10b981";
}

export function UtilityDistribution({ lessons }: UtilityDistributionProps) {
  const data = useMemo(() => {
    const bins = Array.from({ length: 10 }, (_, i) => ({
      range: `${(i * 0.1).toFixed(1)}`,
      count: 0,
      binStart: i * 0.1,
    }));

    for (const lesson of lessons) {
      if (lesson.is_archived) continue;
      const idx = Math.min(Math.floor(lesson.utility * 10), 9);
      bins[idx].count++;
    }

    return bins;
  }, [lessons]);

  if (lessons.length === 0) {
    return (
      <div className="flex h-[200px] items-center justify-center text-sm text-zinc-500">
        No lessons yet
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
        <XAxis
          dataKey="range"
          tick={{ fill: "#a1a1aa", fontSize: 11 }}
          tickLine={false}
          axisLine={{ stroke: "#3f3f46" }}
        />
        <YAxis
          tick={{ fill: "#a1a1aa", fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          allowDecimals={false}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "#18181b",
            border: "1px solid #3f3f46",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelFormatter={(label: string) => `Utility: ${label}`}
          labelStyle={{ color: "#e4e4e7" }}
        />
        <Bar dataKey="count" radius={[4, 4, 0, 0]}>
          {data.map((entry) => (
            <Cell key={entry.range} fill={binColor(entry.binStart)} fillOpacity={0.7} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
