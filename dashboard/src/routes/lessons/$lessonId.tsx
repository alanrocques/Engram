import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { AlertTriangle, ArrowLeft, Archive, CheckCircle, ArchiveRestore } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/page-header";
import { UtilityBadge } from "@/components/lessons/utility-badge";
import { LessonTypeBadge } from "@/components/lessons/lesson-type-badge";
import {
  useLesson,
  useLessonProvenance,
  useArchiveLesson,
  useMarkReviewed,
  useUpdateLesson,
} from "@/hooks/use-lessons";
import { cn, formatDate, formatRelative, confidenceToColor, truncate } from "@/lib/utils";

export const Route = createFileRoute("/lessons/$lessonId")({
  component: LessonDetailPage,
});

// ---------------------------------------------------------------------------
// Local components
// ---------------------------------------------------------------------------

function OutcomeBadge({ outcome }: { outcome: string }) {
  const colors: Record<string, string> = {
    success: "bg-emerald-500/15 text-emerald-400",
    failure: "bg-rose-500/15 text-rose-400",
    partial: "bg-amber-500/15 text-amber-400",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium",
        colors[outcome] ?? "bg-zinc-500/15 text-zinc-400",
      )}
    >
      {outcome}
    </span>
  );
}

function ConfidenceBar({ confidence }: { confidence: number }) {
  const { text } = confidenceToColor(confidence);
  const pct = Math.round(confidence * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 rounded-full bg-white/10">
        <div
          className={cn("h-full rounded-full", {
            "bg-rose-500": confidence < 0.4,
            "bg-amber-500": confidence >= 0.4 && confidence < 0.7,
            "bg-emerald-500": confidence >= 0.7,
          })}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={cn("text-xs tabular-nums", text)}>{pct}%</span>
    </div>
  );
}

function MetadataRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between py-2 border-b border-zinc-800 last:border-0">
      <span className="text-xs text-zinc-500">{label}</span>
      <span className="text-xs text-zinc-300 text-right max-w-[60%]">{children}</span>
    </div>
  );
}

function ProvenanceNode({
  lessonId,
  isCurrent,
  label,
  onClick,
}: {
  lessonId: string;
  isCurrent?: boolean;
  label?: string;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-lg border p-2 text-xs w-36 cursor-pointer text-left",
        isCurrent
          ? "border-blue-500 bg-blue-500/10 text-blue-300"
          : "border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-500",
      )}
    >
      {label ?? lessonId.slice(0, 8) + "..."}
    </button>
  );
}

function ConflictLessonCard({ id }: { id: string }) {
  const { data: conflictLesson, isLoading } = useLesson(id);
  const archiveMutation = useArchiveLesson();

  if (isLoading) return <div className="h-24 animate-pulse rounded bg-zinc-800" />;
  if (!conflictLesson) return null;

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <LessonTypeBadge lessonType={conflictLesson.lesson_type} />
            <OutcomeBadge outcome={conflictLesson.outcome} />
          </div>
          <p className="text-sm text-zinc-300">{conflictLesson.lesson_text}</p>
        </div>
        <div className="flex flex-col gap-2">
          <button
            type="button"
            onClick={() => {
              archiveMutation.mutate(id, {
                onSuccess: () => toast.success("Conflicting lesson archived"),
              });
            }}
            className="rounded bg-rose-500/15 px-2 py-1 text-xs font-medium text-rose-400 hover:bg-rose-500/25"
          >
            Archive This
          </button>
          <Link
            to="/lessons/$lessonId"
            params={{ lessonId: id }}
            className="rounded bg-zinc-800 px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 text-center"
          >
            View
          </Link>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

function LessonDetailPage() {
  const { lessonId } = Route.useParams();
  const navigate = useNavigate();

  const { data: lesson, isLoading } = useLesson(lessonId);
  const { data: provenance, isLoading: provenanceLoading } = useLessonProvenance(lessonId);

  const archiveMutation = useArchiveLesson();
  const markReviewedMutation = useMarkReviewed();
  const updateMutation = useUpdateLesson();

  if (isLoading) {
    return (
      <div>
        <PageHeader title="Lesson Detail" />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_280px]">
          <div className="h-48 animate-pulse rounded-lg bg-zinc-800" />
          <div className="h-48 animate-pulse rounded-lg bg-zinc-800" />
        </div>
      </div>
    );
  }

  if (!lesson) {
    return (
      <div>
        <PageHeader title="Lesson Not Found" />
        <p className="text-sm text-zinc-400">
          Could not find lesson with ID {lessonId}.
        </p>
        <Link
          to="/lessons"
          className="mt-4 inline-flex items-center gap-1.5 text-sm text-blue-400 hover:text-blue-300"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Lessons
        </Link>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Lesson Detail" description={`ID: ${lesson.id}`} />

      {/* Section 1: Content + Metadata */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_280px]">
        {/* Left: Lesson content */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-6">
          <span className="text-xs font-medium text-zinc-500 uppercase tracking-wider">
            Lesson
          </span>
          <p className="mt-3 text-sm leading-relaxed text-zinc-100 whitespace-pre-wrap">
            {lesson.lesson_text}
          </p>
          {lesson.tags.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-1.5">
              {lesson.tags.map((tag) => (
                <span
                  key={tag}
                  className="rounded bg-zinc-800 px-1.5 py-0.5 text-xs text-zinc-400"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
          {lesson.is_archived && (
            <div className="mt-4 rounded bg-zinc-800 px-3 py-2 text-xs text-zinc-400">
              This lesson is archived.
            </div>
          )}
        </div>

        {/* Right: Metadata */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
          <MetadataRow label="Type">
            <LessonTypeBadge lessonType={lesson.lesson_type} />
          </MetadataRow>
          <MetadataRow label="Outcome">
            <OutcomeBadge outcome={lesson.outcome} />
          </MetadataRow>
          <MetadataRow label="Utility">
            <UtilityBadge utility={lesson.utility} showBar />
          </MetadataRow>
          <MetadataRow label="Confidence">
            <ConfidenceBar confidence={lesson.confidence} />
          </MetadataRow>
          <MetadataRow label="Retrievals">
            <span className="tabular-nums">{lesson.retrieval_count}</span>
          </MetadataRow>
          <MetadataRow label="Successes">
            <span className="tabular-nums">{lesson.success_count}</span>
          </MetadataRow>
          <MetadataRow label="Extraction">
            {lesson.extraction_mode ?? "\u2014"}
          </MetadataRow>
          <MetadataRow label="Penalty">
            <span className="flex items-center gap-1">
              {lesson.propagation_penalty > 0.3 && (
                <AlertTriangle className="h-3 w-3 text-amber-500" />
              )}
              <span
                className={cn(
                  "tabular-nums",
                  lesson.propagation_penalty > 0.3 && "text-amber-400",
                )}
              >
                {lesson.propagation_penalty.toFixed(3)}
              </span>
            </span>
          </MetadataRow>
          <MetadataRow label="Agent">{lesson.agent_id}</MetadataRow>
          <MetadataRow label="Domain">{lesson.domain}</MetadataRow>
          <MetadataRow label="Created">{formatDate(lesson.created_at)}</MetadataRow>
          <MetadataRow label="Version">
            <span className="tabular-nums">{lesson.version}</span>
          </MetadataRow>
        </div>
      </div>

      {/* Action buttons */}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Link
          to="/lessons"
          className="inline-flex items-center gap-1.5 rounded bg-zinc-800 px-3 py-1.5 text-sm font-medium text-zinc-300 hover:text-zinc-100"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Lessons
        </Link>

        {lesson.is_archived ? (
          <button
            type="button"
            onClick={() =>
              updateMutation.mutate(
                { id: lessonId, data: { is_archived: false } },
                { onSuccess: () => toast.success("Lesson unarchived") },
              )
            }
            className="inline-flex items-center gap-1.5 rounded bg-emerald-500/15 px-3 py-1.5 text-sm font-medium text-emerald-400 hover:bg-emerald-500/25"
          >
            <ArchiveRestore className="h-3.5 w-3.5" />
            Unarchive
          </button>
        ) : (
          <button
            type="button"
            onClick={() =>
              archiveMutation.mutate(lessonId, {
                onSuccess: () => toast.success("Lesson archived"),
              })
            }
            className="inline-flex items-center gap-1.5 rounded bg-rose-500/15 px-3 py-1.5 text-sm font-medium text-rose-400 hover:bg-rose-500/25"
          >
            <Archive className="h-3.5 w-3.5" />
            Archive
          </button>
        )}

        {lesson.needs_review && (
          <button
            type="button"
            onClick={() =>
              markReviewedMutation.mutate(lessonId, {
                onSuccess: () => toast.success("Marked as reviewed"),
              })
            }
            className="inline-flex items-center gap-1.5 rounded bg-blue-500/15 px-3 py-1.5 text-sm font-medium text-blue-400 hover:bg-blue-500/25"
          >
            <CheckCircle className="h-3.5 w-3.5" />
            Mark Reviewed
          </button>
        )}
      </div>

      {/* Section 2: Provenance Chain + Retrieval History */}
      <div className="mt-8 rounded-lg border border-zinc-800 bg-zinc-900 p-6">
        <h2 className="text-sm font-semibold text-zinc-100 mb-4">Provenance Chain</h2>

        {provenanceLoading ? (
          <div className="h-48 animate-pulse rounded-lg bg-zinc-800" />
        ) : provenance ? (
          <>
            {provenance.parent_lesson_ids.length === 0 &&
            provenance.child_lesson_ids.length === 0 ? (
              <p className="text-xs text-zinc-500">
                No provenance chain — this lesson was created directly.
              </p>
            ) : (
              <div className="flex items-center gap-4 overflow-x-auto py-4">
                {provenance.parent_lesson_ids.length > 0 && (
                  <div className="flex flex-col gap-2">
                    {provenance.parent_lesson_ids.map((id) => (
                      <ProvenanceNode
                        key={id}
                        lessonId={id}
                        onClick={() =>
                          void navigate({
                            to: "/lessons/$lessonId",
                            params: { lessonId: id },
                          })
                        }
                      />
                    ))}
                  </div>
                )}
                {provenance.parent_lesson_ids.length > 0 && (
                  <span className="text-zinc-600 text-lg self-center">&rarr;</span>
                )}

                <ProvenanceNode
                  lessonId={lessonId}
                  isCurrent
                  label={truncate(lesson.lesson_text, 60)}
                />

                {provenance.child_lesson_ids.length > 0 && (
                  <span className="text-zinc-600 text-lg self-center">&rarr;</span>
                )}
                {provenance.child_lesson_ids.length > 0 && (
                  <div className="flex flex-col gap-2">
                    {provenance.child_lesson_ids.map((id) => (
                      <ProvenanceNode
                        key={id}
                        lessonId={id}
                        onClick={() =>
                          void navigate({
                            to: "/lessons/$lessonId",
                            params: { lessonId: id },
                          })
                        }
                      />
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Retrieval History */}
            <h3 className="mt-6 text-sm font-semibold text-zinc-100 mb-3">
              Retrieval History
            </h3>

            {provenance.retrieval_history.length === 0 ? (
              <p className="text-xs text-zinc-500">No retrievals recorded yet.</p>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-zinc-800">
                    <th className="pb-2 text-left font-medium text-zinc-500">
                      Trace ID
                    </th>
                    <th className="pb-2 text-left font-medium text-zinc-500">
                      Retrieved
                    </th>
                    <th className="pb-2 text-left font-medium text-zinc-500">
                      Outcome
                    </th>
                    <th className="pb-2 text-right font-medium text-zinc-500">
                      Reward
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {provenance.retrieval_history.map((r) => (
                    <tr key={r.id} className="border-b border-zinc-800/50">
                      <td className="py-2 font-mono text-zinc-400">
                        {r.trace_id ? r.trace_id.slice(0, 8) : "\u2014"}
                      </td>
                      <td className="py-2 text-zinc-400">
                        {r.retrieved_at ? formatRelative(r.retrieved_at) : "\u2014"}
                      </td>
                      <td className="py-2">
                        {r.outcome ? (
                          <OutcomeBadge outcome={r.outcome} />
                        ) : (
                          <span className="text-zinc-600">&mdash;</span>
                        )}
                      </td>
                      <td className="py-2 text-right tabular-nums text-zinc-300">
                        {r.reward !== null ? r.reward.toFixed(3) : "\u2014"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        ) : (
          <p className="text-xs text-zinc-500">
            Failed to load provenance data.
          </p>
        )}
      </div>

      {/* Section 3: Conflicts (conditional) */}
      {lesson.has_conflict && lesson.conflict_ids.length > 0 && (
        <div className="mt-8 rounded-lg border border-zinc-800 border-l-4 border-l-amber-500 bg-zinc-900 p-6">
          <h2 className="text-sm font-semibold text-zinc-100 mb-2">
            Conflicting Lessons
          </h2>
          <p className="text-xs text-zinc-400 mb-4">
            This lesson has {lesson.conflict_ids.length} conflicting lesson(s).
            Conflicting lessons teach the opposite outcome in a similar context.
          </p>

          <div className="space-y-3">
            {lesson.conflict_ids.map((cid) => (
              <ConflictLessonCard key={cid} id={cid} />
            ))}
          </div>

          <div className="mt-4 flex items-center gap-3">
            <button
              type="button"
              onClick={() =>
                archiveMutation.mutate(lessonId, {
                  onSuccess: () => toast.success("Current lesson archived"),
                })
              }
              className="rounded bg-rose-500/15 px-3 py-1.5 text-xs font-medium text-rose-400 hover:bg-rose-500/25"
            >
              Archive Current Lesson
            </button>
            <button
              type="button"
              onClick={() => toast.success("Both lessons kept")}
              className="rounded bg-zinc-800 px-3 py-1.5 text-xs font-medium text-zinc-400 hover:text-zinc-200"
            >
              Keep Both
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
