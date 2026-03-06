import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Lesson, OverviewStats, Trace } from "@/types/api";

const overviewKeys = {
  all: ["overview"] as const,
  stats: () => [...overviewKeys.all, "stats"] as const,
};

export function useOverviewStats() {
  return useQuery({
    queryKey: overviewKeys.stats(),
    queryFn: async (): Promise<OverviewStats> => {
      const [lessons, traces, flagged, conflicts, fqStats] = await Promise.all([
        api.get<Lesson[]>("/api/v1/lessons", { limit: 1000, include_archived: true }),
        api.get<Trace[]>("/api/v1/traces", { limit: 1000 }),
        api.get<Lesson[]>("/api/v1/lessons/flagged"),
        api.get<{ conflicts: Lesson[]; total: number }>("/api/v1/lessons/conflicts"),
        api.get<{ pending: number }>("/api/v1/failure-queue/stats"),
      ]);

      const byOutcome = { success: 0, failure: 0, partial: 0 };
      let totalConfidence = 0;
      let totalUtility = 0;
      let archivedCount = 0;

      for (const lesson of lessons) {
        if (lesson.outcome in byOutcome) {
          byOutcome[lesson.outcome as keyof typeof byOutcome]++;
        }
        totalConfidence += lesson.confidence;
        totalUtility += lesson.utility;
        if (lesson.is_archived) archivedCount++;
      }

      const count = lessons.length || 1;

      return {
        total_lessons: lessons.length,
        total_traces: traces.length,
        lessons_by_outcome: byOutcome,
        avg_confidence: totalConfidence / count,
        avg_utility: totalUtility / count,
        flagged_count: flagged.length,
        conflict_count: conflicts.total,
        archived_count: archivedCount,
        failure_queue_pending: fqStats.pending,
      };
    },
    refetchInterval: 30_000,
  });
}
