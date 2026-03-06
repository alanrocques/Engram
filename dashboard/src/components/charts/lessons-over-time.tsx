import { useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { Lesson } from "@/types/api";

interface LessonsOverTimeProps {
  lessons: Lesson[];
}

const TYPE_COLORS: Record<string, string> = {
  success_pattern: "#10b981",
  root_cause: "#f43f5e",
  comparative_insight: "#f59e0b",
  general: "#3b82f6",
};

const TYPE_LABELS: Record<string, string> = {
  success_pattern: "Success Pattern",
  root_cause: "Root Cause",
  comparative_insight: "Comparative Insight",
  general: "General",
};

export function LessonsOverTime({ lessons }: LessonsOverTimeProps) {
  const data = useMemo(() => {
    const now = new Date();
    const thirtyDaysAgo = new Date(now);
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

    // Build day buckets
    const days: Record<string, Record<string, number>> = {};
    for (let i = 0; i < 30; i++) {
      const d = new Date(thirtyDaysAgo);
      d.setDate(d.getDate() + i);
      const key = d.toISOString().slice(0, 10);
      days[key] = { success_pattern: 0, root_cause: 0, comparative_insight: 0, general: 0 };
    }

    for (const lesson of lessons) {
      const dayKey = lesson.created_at.slice(0, 10);
      if (days[dayKey]) {
        const type = lesson.lesson_type in TYPE_COLORS ? lesson.lesson_type : "general";
        days[dayKey][type]++;
      }
    }

    return Object.entries(days)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, counts]) => ({
        date: new Date(date).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
        ...counts,
      }));
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
      <AreaChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis
          dataKey="date"
          tick={{ fill: "#a1a1aa", fontSize: 11 }}
          tickLine={false}
          axisLine={{ stroke: "#3f3f46" }}
          interval="preserveStartEnd"
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
          labelStyle={{ color: "#e4e4e7" }}
        />
        {Object.entries(TYPE_COLORS).map(([type, color]) => (
          <Area
            key={type}
            type="monotone"
            dataKey={type}
            stackId="1"
            stroke={color}
            fill={color}
            fillOpacity={0.3}
            name={TYPE_LABELS[type] ?? type}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}
