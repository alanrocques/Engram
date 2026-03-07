import { useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/page-header";
import { UtilityBadge } from "@/components/lessons/utility-badge";
import { LessonTypeBadge } from "@/components/lessons/lesson-type-badge";
import {
  useFlaggedLessons,
  useConflictingLessons,
  useArchiveLesson,
  useMarkReviewed,
} from "@/hooks/use-lessons";
import { cn, truncate } from "@/lib/utils";

export const Route = createFileRoute("/flagged")({
  component: ReviewPage,
});

function ReviewPage() {
  const [activeTab, setActiveTab] = useState<"flagged" | "conflicts">("flagged");
  const { data: flaggedLessons, isLoading: flaggedLoading } = useFlaggedLessons();
  const { data: conflictData, isLoading: conflictsLoading } = useConflictingLessons();
  const archiveLesson = useArchiveLesson();
  const markReviewed = useMarkReviewed();

  const conflicts = conflictData?.conflicts ?? [];

  return (
    <div>
      <PageHeader
        title="Review Queue"
        description="Lessons flagged for review and conflict resolution"
      />

      {/* Tab Bar */}
      <div className="mb-6 flex border-b border-zinc-800">
        <TabButton
          tab="flagged"
          label="Flagged"
          count={flaggedLessons?.length ?? 0}
          activeTab={activeTab}
          onClick={() => setActiveTab("flagged")}
        />
        <TabButton
          tab="conflicts"
          label="Conflicts"
          count={conflictData?.total ?? 0}
          activeTab={activeTab}
          onClick={() => setActiveTab("conflicts")}
        />
      </div>

      {activeTab === "flagged" ? (
        <FlaggedTab
          lessons={flaggedLessons ?? []}
          isLoading={flaggedLoading}
          archiveLesson={archiveLesson}
          markReviewed={markReviewed}
        />
      ) : (
        <ConflictsTab
          conflicts={conflicts}
          isLoading={conflictsLoading}
          archiveLesson={archiveLesson}
        />
      )}
    </div>
  );
}

function TabButton({
  tab,
  label,
  count,
  activeTab,
  onClick,
}: {
  tab: string;
  label: string;
  count: number;
  activeTab: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors",
        activeTab === tab
          ? "border-blue-500 text-zinc-100"
          : "border-transparent text-zinc-500 hover:text-zinc-300",
      )}
    >
      {label}
      {count > 0 && (
        <span
          className={cn(
            "rounded-full px-1.5 py-0.5 text-xs font-medium",
            activeTab === tab ? "bg-blue-500/20 text-blue-400" : "bg-zinc-800 text-zinc-500",
          )}
        >
          {count}
        </span>
      )}
    </button>
  );
}

function FlaggedTab({
  lessons,
  isLoading,
  archiveLesson,
  markReviewed,
}: {
  lessons: Array<{
    id: string;
    lesson_type: string;
    lesson_text: string;
    propagation_penalty: number;
    review_reason: string | null;
    utility: number;
    retrieval_count: number;
  }>;
  isLoading: boolean;
  archiveLesson: ReturnType<typeof useArchiveLesson>;
  markReviewed: ReturnType<typeof useMarkReviewed>;
}) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-20 animate-pulse rounded-lg bg-zinc-800" />
        ))}
      </div>
    );
  }

  if (lessons.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-16 text-zinc-500">
        <CheckCircle2 className="h-10 w-10" />
        <span>No lessons flagged for review</span>
      </div>
    );
  }

  return (
    <div className="divide-y divide-zinc-800 rounded-lg border border-zinc-800 bg-zinc-900">
      {lessons.map((lesson) => (
        <div key={lesson.id} className="flex items-start gap-4 px-4 py-4">
          <div className="min-w-0 flex-1">
            <div className="mb-1 flex items-center gap-2">
              <LessonTypeBadge lessonType={lesson.lesson_type} />
              {lesson.propagation_penalty > 0.3 && (
                <span className="flex items-center gap-1 text-xs text-amber-400">
                  <AlertTriangle className="h-3 w-3" />
                  {lesson.propagation_penalty.toFixed(2)} penalty
                </span>
              )}
            </div>
            <p className="text-sm text-zinc-300">{truncate(lesson.lesson_text, 120)}</p>
            {lesson.review_reason && (
              <p className="mt-1 text-xs text-amber-500">Reason: {lesson.review_reason}</p>
            )}
            <div className="mt-2 flex items-center gap-3">
              <UtilityBadge utility={lesson.utility} showBar />
              <span className="text-xs text-zinc-500">{lesson.retrieval_count} retrievals</span>
            </div>
          </div>
          <div className="flex flex-shrink-0 flex-col gap-2">
            <button
              onClick={() => {
                markReviewed.mutate(lesson.id, {
                  onSuccess: () => toast.success("Marked as reviewed"),
                });
              }}
              disabled={markReviewed.isPending}
              className="rounded bg-blue-500/15 px-2 py-1 text-xs font-medium text-blue-400 hover:bg-blue-500/25 disabled:opacity-50"
            >
              Mark Reviewed
            </button>
            <button
              onClick={() => {
                archiveLesson.mutate(lesson.id, {
                  onSuccess: () => toast.success("Lesson archived"),
                });
              }}
              disabled={archiveLesson.isPending}
              className="rounded bg-rose-500/15 px-2 py-1 text-xs font-medium text-rose-400 hover:bg-rose-500/25 disabled:opacity-50"
            >
              Archive
            </button>
            <Link
              to="/lessons/$lessonId"
              params={{ lessonId: lesson.id }}
              className="rounded bg-zinc-800 px-2 py-1 text-center text-xs text-zinc-400 hover:text-zinc-200"
            >
              View Detail
            </Link>
          </div>
        </div>
      ))}
    </div>
  );
}

function ConflictsTab({
  conflicts,
  isLoading,
  archiveLesson,
}: {
  conflicts: Array<{
    id: string;
    lesson_type: string;
    lesson_text: string;
    outcome: string;
    utility: number;
    conflict_ids: string[];
  }>;
  isLoading: boolean;
  archiveLesson: ReturnType<typeof useArchiveLesson>;
}) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-32 animate-pulse rounded-lg bg-zinc-800" />
        ))}
      </div>
    );
  }

  if (conflicts.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-16 text-zinc-500">
        <CheckCircle2 className="h-10 w-10" />
        <span>No conflicting lessons detected</span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {conflicts.map((lesson) => (
        <div
          key={lesson.id}
          className="rounded-lg border border-amber-500/30 bg-zinc-900 p-4"
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <div className="mb-2 flex items-center gap-2">
                <LessonTypeBadge lessonType={lesson.lesson_type} />
                <span
                  className={cn(
                    "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium",
                    lesson.outcome === "success"
                      ? "bg-emerald-500/15 text-emerald-400"
                      : lesson.outcome === "failure"
                        ? "bg-rose-500/15 text-rose-400"
                        : "bg-amber-500/15 text-amber-400",
                  )}
                >
                  {lesson.outcome}
                </span>
                <UtilityBadge utility={lesson.utility} />
              </div>
              <p className="mb-2 text-sm text-zinc-300">{lesson.lesson_text}</p>
              <p className="text-xs text-zinc-500">
                Conflicts with {lesson.conflict_ids.length} other lesson
                {lesson.conflict_ids.length > 1 ? "s" : ""}
              </p>
            </div>
            <div className="flex flex-shrink-0 flex-col gap-2">
              <button
                onClick={() => {
                  archiveLesson.mutate(lesson.id, {
                    onSuccess: () => toast.success("Lesson archived"),
                  });
                }}
                className="rounded bg-rose-500/15 px-2 py-1 text-xs font-medium text-rose-400 hover:bg-rose-500/25"
              >
                Archive This
              </button>
              <button
                onClick={() => {
                  lesson.conflict_ids.forEach((cid) => {
                    archiveLesson.mutate(cid);
                  });
                  toast.success("Conflicting lessons archived");
                }}
                className="rounded bg-zinc-800 px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200"
              >
                Archive Conflicts
              </button>
              <Link
                to="/lessons/$lessonId"
                params={{ lessonId: lesson.id }}
                className="rounded bg-zinc-800 px-2 py-1 text-center text-xs text-zinc-400 hover:text-zinc-200"
              >
                View Detail
              </Link>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
