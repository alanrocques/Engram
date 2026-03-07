import { createFileRoute, Link } from "@tanstack/react-router";
import { AlertTriangle, Play, Loader2, CheckCircle2, BookOpen } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/page-header";
import { useFailureQueueStats, useTriggerBatchAnalysis } from "@/hooks/use-failure-queue";
import { useLessons } from "@/hooks/use-lessons";
import { cn, formatRelative } from "@/lib/utils";

export const Route = createFileRoute("/failure-queue")({
  component: FailureQueuePage,
});

function FailureQueuePage() {
  const { data: stats, isLoading: statsLoading } = useFailureQueueStats();
  const triggerMutation = useTriggerBatchAnalysis();
  const { data: lessons, isLoading: lessonsLoading } = useLessons({ limit: 50 });

  const rootCauseLessons = (lessons ?? [])
    .filter((l) => l.lesson_type === "root_cause")
    .slice(0, 5);

  return (
    <div>
      <PageHeader
        title="Failure Queue"
        description="Grouped failure traces awaiting batch analysis"
      />

      {/* Stats Row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {statsLoading || !stats ? (
          <>
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-28 animate-pulse rounded-lg bg-zinc-800" />
            ))}
          </>
        ) : (
          <>
            {/* Pending Count */}
            <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                Pending Failures
              </p>
              <p
                className={cn(
                  "mt-2 text-4xl font-bold tabular-nums",
                  stats.pending > 20
                    ? "text-rose-400"
                    : stats.pending > 5
                      ? "text-amber-400"
                      : "text-zinc-100",
                )}
              >
                {stats.pending}
              </p>
              {stats.pending > 20 && (
                <p className="mt-1 flex items-center gap-1 text-xs text-rose-400">
                  <AlertTriangle className="h-3 w-3" /> Queue backlog is high
                </p>
              )}
            </div>

            {/* Top Categories */}
            <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
              <p className="mb-3 text-xs font-medium uppercase tracking-wide text-zinc-500">
                Top Categories
              </p>
              <div className="space-y-1.5">
                {Object.entries(stats.by_category)
                  .sort(([, a], [, b]) => b - a)
                  .slice(0, 3)
                  .map(([cat, count]) => (
                    <div key={cat} className="flex items-center justify-between text-sm">
                      <span className="truncate text-zinc-400">{cat}</span>
                      <span className="ml-2 tabular-nums text-zinc-200">{count}</span>
                    </div>
                  ))}
                {Object.keys(stats.by_category).length === 0 && (
                  <p className="text-sm text-zinc-600">No failures categorized</p>
                )}
              </div>
            </div>

            {/* Batch Analysis Trigger */}
            <div className="flex flex-col justify-between rounded-lg border border-zinc-800 bg-zinc-900 p-4">
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                  Batch Analysis
                </p>
                <p className="mt-1 text-xs text-zinc-500">
                  Groups with 3+ failures of the same signature will be analyzed.
                </p>
              </div>
              <button
                onClick={() => {
                  triggerMutation.mutate(undefined, {
                    onSuccess: () => toast.success("Batch analysis started"),
                    onError: () => toast.error("Failed to start analysis"),
                  });
                }}
                disabled={triggerMutation.isPending}
                className="mt-3 flex items-center justify-center gap-2 rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
              >
                {triggerMutation.isPending ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" /> Running...
                  </>
                ) : (
                  <>
                    <Play className="h-3.5 w-3.5" /> Run Batch Analysis Now
                  </>
                )}
              </button>
            </div>
          </>
        )}
      </div>

      {/* Error Signatures */}
      <div className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900">
        <div className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-medium text-zinc-100">Error Signatures</h2>
          <p className="mt-0.5 text-xs text-zinc-500">
            Grouped by failure pattern — groups with 3+ are ready for batch analysis
          </p>
        </div>
        {statsLoading || !stats ? (
          <div className="divide-y divide-zinc-800/50">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="px-4 py-3">
                <div className="h-4 animate-pulse rounded bg-zinc-800" />
              </div>
            ))}
          </div>
        ) : (
          <div className="divide-y divide-zinc-800">
            {Object.entries(stats.by_signature)
              .sort(([, a], [, b]) => b - a)
              .slice(0, 10)
              .map(([sig, count]) => (
                <div key={sig} className="flex items-center justify-between px-4 py-3">
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="truncate font-mono text-xs text-zinc-400">{sig}</span>
                    {count >= 3 && (
                      <span className="flex-shrink-0 rounded-full bg-blue-500/15 px-2 py-0.5 text-xs font-medium text-blue-400">
                        Ready for analysis
                      </span>
                    )}
                  </div>
                  <span className="ml-4 flex-shrink-0 tabular-nums text-sm font-medium text-zinc-200">
                    {count}
                  </span>
                </div>
              ))}
            {Object.keys(stats.by_signature).length === 0 && (
              <div className="flex flex-col items-center gap-2 py-12 text-zinc-500">
                <CheckCircle2 className="h-8 w-8" />
                <span className="text-sm">No pending failure signatures</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Recent Root Cause Lessons */}
      <div className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900">
        <div className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-medium text-zinc-100">Recently Extracted Root Causes</h2>
        </div>
        {lessonsLoading ? (
          <div className="divide-y divide-zinc-800/50">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="px-4 py-3">
                <div className="h-4 animate-pulse rounded bg-zinc-800" />
              </div>
            ))}
          </div>
        ) : rootCauseLessons.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-12 text-zinc-500">
            <BookOpen className="h-8 w-8" />
            <span className="text-sm">No root cause lessons yet</span>
          </div>
        ) : (
          <div className="divide-y divide-zinc-800">
            {rootCauseLessons.map((lesson) => (
              <div
                key={lesson.id}
                className="flex items-start justify-between gap-3 px-4 py-3"
              >
                <div className="min-w-0 flex-1">
                  <p className="line-clamp-2 text-sm text-zinc-300">{lesson.lesson_text}</p>
                  <p className="mt-1 text-xs text-zinc-500">
                    {formatRelative(lesson.created_at)}
                  </p>
                </div>
                <Link
                  to="/lessons/$lessonId"
                  params={{ lessonId: lesson.id }}
                  className="flex-shrink-0 rounded bg-zinc-800 px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200"
                >
                  View
                </Link>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
