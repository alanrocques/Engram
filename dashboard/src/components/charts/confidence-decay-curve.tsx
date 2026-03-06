import { useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { Lesson } from "@/types/api";

interface ConfidenceDecayCurveProps {
  lessons: Lesson[];
}

const AGE_BUCKETS = [
  { label: "0-7d", maxDays: 7 },
  { label: "7-14d", maxDays: 14 },
  { label: "14-30d", maxDays: 30 },
  { label: "30-60d", maxDays: 60 },
  { label: "60-90d", maxDays: 90 },
  { label: "90+d", maxDays: Infinity },
];

export function ConfidenceDecayCurve({ lessons }: ConfidenceDecayCurveProps) {
  const data = useMemo(() => {
    const now = Date.now();
    const buckets = AGE_BUCKETS.map((b) => ({ ...b, total: 0, count: 0 }));

    for (const lesson of lessons) {
      if (lesson.is_archived) continue;
      const ageDays = (now - new Date(lesson.created_at).getTime()) / (1000 * 60 * 60 * 24);
      let prevMax = 0;
      for (const bucket of buckets) {
        if (ageDays >= prevMax && (ageDays < bucket.maxDays || bucket.maxDays === Infinity)) {
          bucket.total += lesson.confidence;
          bucket.count++;
          break;
        }
        prevMax = bucket.maxDays;
      }
    }

    return buckets.map((b) => ({
      age: b.label,
      confidence: b.count > 0 ? Number((b.total / b.count).toFixed(3)) : null,
    }));
  }, [lessons]);

  const hasData = data.some((d) => d.confidence !== null);

  if (!hasData) {
    return (
      <div className="flex h-[200px] items-center justify-center text-sm text-zinc-500">
        No confidence data
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis
          dataKey="age"
          tick={{ fill: "#a1a1aa", fontSize: 11 }}
          tickLine={false}
          axisLine={{ stroke: "#3f3f46" }}
        />
        <YAxis
          domain={[0, 1]}
          tick={{ fill: "#a1a1aa", fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "#18181b",
            border: "1px solid #3f3f46",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelStyle={{ color: "#e4e4e7" }}
          formatter={(value: number) => [`${Math.round(value * 100)}%`, "Avg Confidence"]}
        />
        <Line
          type="monotone"
          dataKey="confidence"
          stroke="#3b82f6"
          strokeWidth={2}
          dot={{ fill: "#3b82f6", r: 4 }}
          connectNulls
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
