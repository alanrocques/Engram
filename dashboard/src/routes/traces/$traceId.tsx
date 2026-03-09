import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft, RefreshCw, Zap } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/page-header";
import { SpanWaterfall } from "@/components/traces/span-waterfall";
import { useTrace, useProcessTrace } from "@/hooks/use-traces";
import { cn, formatDateTime, formatRelative } from "@/lib/utils";

export const Route = createFileRoute("/traces/$traceId")({
  component: TraceDetailPage,
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

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    pending: "bg-amber-500/15 text-amber-400",
    processed: "bg-emerald-500/15 text-emerald-400",
    failed: "bg-rose-500/15 text-rose-400",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium",
        colors[status] ?? "bg-zinc-500/15 text-zinc-400",
      )}
    >
      {status}
    </span>
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

// ---------------------------------------------------------------------------
// Span type extraction
// ---------------------------------------------------------------------------

interface Span {
  name: string;
  status: string;
  duration_ms: number;
  attributes?: Record<string, unknown>;
}

function extractSpans(traceData: Record<string, unknown> | null | undefined): Span[] {
  if (!traceData) return [];

  // Try trace_data.spans first
  const spans = traceData["spans"];
  if (Array.isArray(spans)) {
    return spans.map((s: unknown) => {
      const span = s as Record<string, unknown>;
      return {
        name: String(span["name"] ?? "unknown"),
        status: String(span["status"] ?? "unknown"),
        duration_ms: Number(span["duration_ms"] ?? 0),
        attributes: (span["attributes"] as Record<string, unknown>) ?? undefined,
      };
    });
  }

  // Try trace_data.result.spans
  const result = traceData["result"] as Record<string, unknown> | undefined;
  if (result && Array.isArray(result["spans"])) {
    return (result["spans"] as unknown[]).map((s: unknown) => {
      const span = s as Record<string, unknown>;
      return {
        name: String(span["name"] ?? "unknown"),
        status: String(span["status"] ?? "unknown"),
        duration_ms: Number(span["duration_ms"] ?? 0),
        attributes: (span["attributes"] as Record<string, unknown>) ?? undefined,
      };
    });
  }

  return [];
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

function TraceDetailPage() {
  const { traceId } = Route.useParams();
  const { data: trace, isLoading } = useTrace(traceId);
  const processTrace = useProcessTrace();

  if (isLoading) {
    return (
      <div>
        <PageHeader title="Trace Detail" />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_280px]">
          <div className="h-48 animate-pulse rounded-lg bg-zinc-800" />
          <div className="h-48 animate-pulse rounded-lg bg-zinc-800" />
        </div>
      </div>
    );
  }

  if (!trace) {
    return (
      <div>
        <PageHeader title="Trace Not Found" />
        <p className="text-sm text-zinc-400">
          Could not find trace with ID {traceId}.
        </p>
        <Link
          to="/traces"
          className="mt-4 inline-flex items-center gap-1.5 text-sm text-blue-400 hover:text-blue-300"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Traces
        </Link>
      </div>
    );
  }

  const spans = extractSpans(trace.trace_data);

  return (
    <div>
      <PageHeader title="Trace Detail" description={`ID: ${trace.id}`} />

      {/* Metadata + Actions */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_280px]">
        {/* Left: Span Waterfall */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-6">
          <span className="text-xs font-medium text-zinc-500 uppercase tracking-wider">
            Span Waterfall
          </span>
          <div className="mt-4">
            {spans.length > 0 ? (
              <SpanWaterfall spans={spans} />
            ) : (
              <p className="text-xs text-zinc-500">
                No span data available for this trace.
              </p>
            )}
          </div>
        </div>

        {/* Right: Metadata */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
          <MetadataRow label="Agent">{trace.agent_id}</MetadataRow>
          <MetadataRow label="Outcome">
            {trace.outcome ? (
              <OutcomeBadge outcome={trace.outcome} />
            ) : (
              <span className="text-zinc-500">&mdash;</span>
            )}
          </MetadataRow>
          <MetadataRow label="Status">
            <StatusBadge status={trace.status} />
          </MetadataRow>
          <MetadataRow label="Spans">
            <span className="tabular-nums">{trace.span_count}</span>
          </MetadataRow>
          <MetadataRow label="Created">
            {formatDateTime(trace.created_at)}
          </MetadataRow>
          <MetadataRow label="Processed">
            {trace.processed_at ? formatRelative(trace.processed_at) : "\u2014"}
          </MetadataRow>
          <MetadataRow label="Content Hash">
            {trace.content_hash ? (
              <span className="font-mono text-[10px] break-all">
                {trace.content_hash}
              </span>
            ) : (
              "\u2014"
            )}
          </MetadataRow>
          <MetadataRow label="Extraction">
            {trace.extraction_mode ?? "\u2014"}
          </MetadataRow>
          <MetadataRow label="Memory">
            {trace.is_influenced ? (
              <span className="flex items-center gap-1">
                <Zap className="h-3 w-3 text-blue-400" />
                <span className="text-blue-400">Influenced</span>
              </span>
            ) : (
              "No"
            )}
          </MetadataRow>
        </div>
      </div>

      {/* Action buttons */}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Link
          to="/traces"
          className="inline-flex items-center gap-1.5 rounded bg-zinc-800 px-3 py-1.5 text-sm font-medium text-zinc-300 hover:text-zinc-100"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Traces
        </Link>

        <button
          type="button"
          onClick={() =>
            processTrace.mutate(traceId, {
              onSuccess: () => toast.success("Trace re-processing queued"),
              onError: () => toast.error("Failed to re-process trace"),
            })
          }
          disabled={processTrace.isPending}
          className={cn(
            "inline-flex items-center gap-1.5 rounded bg-blue-500/15 px-3 py-1.5 text-sm font-medium text-blue-400 hover:bg-blue-500/25",
            processTrace.isPending && "opacity-50 cursor-not-allowed",
          )}
        >
          <RefreshCw className={cn("h-3.5 w-3.5", processTrace.isPending && "animate-spin")} />
          Re-process
        </button>
      </div>

      {/* Retrieved Lessons */}
      {trace.retrieved_lesson_ids && trace.retrieved_lesson_ids.length > 0 && (
        <div className="mt-8 rounded-lg border border-zinc-800 bg-zinc-900 p-6">
          <h2 className="text-sm font-semibold text-zinc-100 mb-3">
            Retrieved Lessons
          </h2>
          <div className="flex flex-wrap gap-2">
            {trace.retrieved_lesson_ids.map((lid) => (
              <Link
                key={lid}
                to="/lessons/$lessonId"
                params={{ lessonId: lid }}
                className="rounded bg-blue-500/15 px-2.5 py-1 font-mono text-xs text-blue-400 hover:bg-blue-500/25 transition-colors"
              >
                {lid.slice(0, 8)}...
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
