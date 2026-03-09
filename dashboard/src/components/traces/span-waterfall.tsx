import { useState } from "react";
import { cn } from "@/lib/utils";

interface Span {
  name: string;
  status: string;
  duration_ms: number;
  attributes?: Record<string, unknown>;
}

interface SpanWaterfallProps {
  spans: Span[];
}

function statusColor(status: string): {
  bar: string;
  text: string;
} {
  switch (status) {
    case "ok":
      return { bar: "bg-emerald-500", text: "text-emerald-400" };
    case "error":
      return { bar: "bg-rose-500", text: "text-rose-400" };
    default:
      return { bar: "bg-amber-500", text: "text-amber-400" };
  }
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

export function SpanWaterfall({ spans }: SpanWaterfallProps) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  if (spans.length === 0) {
    return (
      <p className="text-xs text-zinc-500">No spans available.</p>
    );
  }

  // Calculate cumulative offsets (sequential spans)
  const offsets: number[] = [];
  let cumulative = 0;
  for (const span of spans) {
    offsets.push(cumulative);
    cumulative += span.duration_ms;
  }
  const totalDuration = cumulative;

  // Generate timeline tick marks
  const tickCount = Math.min(5, Math.max(2, Math.ceil(totalDuration / 200)));
  const tickInterval = totalDuration / tickCount;
  const ticks: number[] = [];
  for (let i = 0; i <= tickCount; i++) {
    ticks.push(Math.round(i * tickInterval));
  }

  const LABEL_WIDTH = 180;

  return (
    <div className="overflow-x-auto">
      {/* Timeline header */}
      <div className="flex items-end mb-1" style={{ paddingLeft: LABEL_WIDTH }}>
        <div className="relative w-full h-5">
          {ticks.map((tick) => {
            const pct = totalDuration > 0 ? (tick / totalDuration) * 100 : 0;
            return (
              <span
                key={tick}
                className="absolute text-[10px] text-zinc-500 -translate-x-1/2"
                style={{ left: `${pct}%` }}
              >
                {formatDuration(tick)}
              </span>
            );
          })}
        </div>
      </div>

      {/* Span rows */}
      <div className="space-y-0.5">
        {spans.map((span, i) => {
          const offset = offsets[i];
          const leftPct = totalDuration > 0 ? (offset / totalDuration) * 100 : 0;
          const widthPct = totalDuration > 0 ? (span.duration_ms / totalDuration) * 100 : 100;
          const color = statusColor(span.status);
          const isExpanded = expandedIndex === i;
          const hasAttrs = span.attributes && Object.keys(span.attributes).length > 0;

          return (
            <div key={i}>
              <button
                type="button"
                onClick={() => setExpandedIndex(isExpanded ? null : i)}
                className={cn(
                  "flex w-full items-center gap-0 rounded py-1.5 text-left transition-colors",
                  hasAttrs ? "hover:bg-zinc-800/50 cursor-pointer" : "cursor-default",
                  isExpanded && "bg-zinc-800/50",
                )}
              >
                {/* Span name label */}
                <div
                  className="flex-shrink-0 truncate px-2 text-xs text-zinc-300"
                  style={{ width: LABEL_WIDTH }}
                  title={span.name}
                >
                  {span.name}
                </div>

                {/* Bar area */}
                <div className="relative flex-1 h-6">
                  {/* Background track */}
                  <div className="absolute inset-0 rounded bg-zinc-800/30" />

                  {/* Span bar */}
                  <div
                    className={cn("absolute top-0.5 h-5 rounded", color.bar)}
                    style={{
                      left: `${leftPct}%`,
                      width: `max(${widthPct}%, 2px)`,
                    }}
                  >
                    {/* Duration label */}
                    <span
                      className={cn(
                        "absolute top-0.5 whitespace-nowrap text-[10px] font-medium",
                        widthPct > 12
                          ? "left-1.5 text-white"
                          : `left-[calc(100%+4px)] ${color.text}`,
                      )}
                    >
                      {formatDuration(span.duration_ms)}
                    </span>
                  </div>
                </div>
              </button>

              {/* Expanded attributes */}
              {isExpanded && hasAttrs && (
                <div
                  className="mb-1 ml-2 rounded border border-zinc-800 bg-zinc-900/80 p-3"
                  style={{ marginLeft: LABEL_WIDTH }}
                >
                  <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
                    {Object.entries(span.attributes!).map(([key, value]) => (
                      <div key={key} className="contents">
                        <span className="text-[11px] text-zinc-500">{key}</span>
                        <span className="text-[11px] text-zinc-300 font-mono break-all">
                          {typeof value === "object" ? JSON.stringify(value) : String(value)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Total duration */}
      <div className="mt-2 flex justify-end">
        <span className="text-[11px] text-zinc-500">
          Total: {formatDuration(totalDuration)}
        </span>
      </div>
    </div>
  );
}
