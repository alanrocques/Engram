import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { BookOpen } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { useOverviewStats } from "@/hooks/use-overview-stats";
import { useLessons } from "@/hooks/use-lessons";
import { LessonsOverTime } from "@/components/charts/lessons-over-time";
import { UtilityDistribution } from "@/components/charts/utility-distribution";
import { OutcomeBreakdown } from "@/components/charts/outcome-breakdown";
import { ConfidenceDecayCurve } from "@/components/charts/confidence-decay-curve";
import { LessonTypeBadge } from "@/components/lessons/lesson-type-badge";
import { cn } from "@/lib/utils";
import { formatRelative, truncate } from "@/lib/utils";

export const Route = createFileRoute("/")({
  component: OverviewPage,
});

function KpiCardSkeleton() {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4 h-24 animate-pulse" />
  );
}

function ChartSkeleton() {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
      <div className="mb-3">
        <div className="h-4 w-28 animate-pulse rounded bg-zinc-800" />
        <div className="mt-1.5 h-3 w-20 animate-pulse rounded bg-zinc-800" />
      </div>
      <div className="h-[200px] animate-pulse rounded-lg bg-zinc-800" />
    </div>
  );
}

function ActivitySkeleton() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 10 }, (_, i) => (
        <div key={i} className="h-8 animate-pulse rounded bg-zinc-800" />
      ))}
    </div>
  );
}

function utilityColor(value: number): string {
  if (value >= 0.7) return "text-emerald-400";
  if (value >= 0.3) return "text-amber-400";
  return "text-rose-400";
}

function queueColor(count: number): string {
  if (count > 20) return "text-rose-400";
  if (count > 5) return "text-amber-400";
  return "text-zinc-100";
}

function OverviewPage() {
  const { data: stats, isLoading: statsLoading } = useOverviewStats();
  const { data: allLessons, isLoading: lessonsLoading } = useLessons({
    limit: 1000,
    include_archived: false,
  });
  const { data: recentLessons, isLoading: recentLoading } = useLessons({
    limit: 10,
  });
  const navigate = useNavigate();

  return (
    <div>
      <PageHeader
        title="Overview"
        description="System-wide memory health and activity"
      />

      {/* KPI Cards */}
      <div className="grid grid-cols-4 gap-4">
        {statsLoading ? (
          <>
            <KpiCardSkeleton />
            <KpiCardSkeleton />
            <KpiCardSkeleton />
            <KpiCardSkeleton />
          </>
        ) : stats ? (
          <>
            {/* Total Active Lessons */}
            <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
              <p className="text-2xl font-semibold text-zinc-100">
                {stats.total_lessons - stats.archived_count}
              </p>
              <p className="mt-1 text-xs text-zinc-500">active lessons</p>
            </div>

            {/* Average Utility */}
            <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
              <p className={cn("text-2xl font-semibold", utilityColor(stats.avg_utility))}>
                {(stats.avg_utility * 100).toFixed(1)}%
              </p>
              <p className="mt-1 text-xs text-zinc-500">avg utility score</p>
            </div>

            {/* Failure Queue Depth */}
            <Link
              to="/failure-queue"
              className="rounded-lg border border-zinc-800 bg-zinc-900 p-4 transition-colors hover:border-zinc-700"
            >
              <div className="flex items-center gap-2">
                <p className={cn("text-2xl font-semibold", queueColor(stats.failure_queue_pending))}>
                  {stats.failure_queue_pending}
                </p>
                {stats.failure_queue_pending > 20 && (
                  <span className="rounded bg-rose-500/20 px-1.5 py-0.5 text-[10px] font-medium text-rose-400">
                    Needs attention
                  </span>
                )}
              </div>
              <p className="mt-1 text-xs text-zinc-500">pending failures</p>
            </Link>

            {/* Flagged for Review */}
            <Link
              to="/flagged"
              className="rounded-lg border border-zinc-800 bg-zinc-900 p-4 transition-colors hover:border-zinc-700"
            >
              <p className={cn(
                "text-2xl font-semibold",
                stats.flagged_count > 0 ? "text-amber-400" : "text-zinc-100",
              )}>
                {stats.flagged_count}
              </p>
              <p className="mt-1 text-xs text-zinc-500">flagged lessons</p>
            </Link>
          </>
        ) : null}
      </div>

      {/* Charts Grid */}
      <div className="mt-6 grid grid-cols-2 gap-4">
        {lessonsLoading || statsLoading ? (
          <>
            <ChartSkeleton />
            <ChartSkeleton />
            <ChartSkeleton />
            <ChartSkeleton />
          </>
        ) : (
          <>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
              <div className="mb-3">
                <p className="text-sm font-medium text-zinc-100">Lesson Creation</p>
                <p className="text-xs text-zinc-500">Past 30 days</p>
              </div>
              <LessonsOverTime lessons={allLessons ?? []} />
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
              <div className="mb-3">
                <p className="text-sm font-medium text-zinc-100">Utility Distribution</p>
                <p className="text-xs text-zinc-500">Active lessons</p>
              </div>
              <UtilityDistribution lessons={allLessons ?? []} />
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
              <div className="mb-3">
                <p className="text-sm font-medium text-zinc-100">Outcome Breakdown</p>
                <p className="text-xs text-zinc-500">All traces</p>
              </div>
              <OutcomeBreakdown
                outcomes={stats?.lessons_by_outcome ?? { success: 0, failure: 0, partial: 0 }}
              />
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
              <div className="mb-3">
                <p className="text-sm font-medium text-zinc-100">Confidence Decay</p>
                <p className="text-xs text-zinc-500">By lesson age</p>
              </div>
              <ConfidenceDecayCurve lessons={allLessons ?? []} />
            </div>
          </>
        )}
      </div>

      {/* Recent Activity Feed */}
      <div className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
        <p className="mb-3 text-sm font-medium text-zinc-100">Recent Activity</p>
        {recentLoading ? (
          <ActivitySkeleton />
        ) : !recentLessons || recentLessons.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-zinc-500">
            <BookOpen className="mb-2 h-8 w-8" />
            <p className="text-sm">No lessons yet</p>
          </div>
        ) : (
          <div className="space-y-0.5">
            {recentLessons.map((lesson) => (
              <button
                key={lesson.id}
                type="button"
                onClick={() => {
                  void navigate({ to: "/lessons/$lessonId", params: { lessonId: lesson.id } });
                }}
                className="flex w-full items-center gap-3 rounded px-2 py-1.5 text-left transition-colors hover:bg-zinc-800/50"
              >
                <LessonTypeBadge lessonType={lesson.lesson_type} />
                <span className="flex-1 truncate text-sm text-zinc-300">
                  {truncate(lesson.lesson_text, 60)}
                </span>
                <span className="shrink-0 text-xs text-zinc-500">
                  {formatRelative(lesson.created_at)}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
