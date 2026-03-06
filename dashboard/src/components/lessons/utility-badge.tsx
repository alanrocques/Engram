import { cn, utilityToColor } from "@/lib/utils";

interface UtilityBadgeProps {
  utility: number;
  showBar?: boolean;
  className?: string;
}

export function UtilityBadge({
  utility,
  showBar = true,
  className,
}: UtilityBadgeProps) {
  const { bg, text, label } = utilityToColor(utility);
  const pct = Math.round(utility * 100);

  return (
    <div className={cn("flex items-center gap-2", className)}>
      {showBar && (
        <div className="h-1.5 w-16 rounded-full bg-white/10">
          <div
            className={cn("h-full rounded-full transition-all", {
              "bg-rose-500": utility < 0.3,
              "bg-amber-500": utility >= 0.3 && utility < 0.7,
              "bg-emerald-500": utility >= 0.7,
            })}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
      <span
        className={cn(
          "inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-medium tabular-nums",
          bg,
          text,
        )}
      >
        {label} {pct}%
      </span>
    </div>
  );
}
