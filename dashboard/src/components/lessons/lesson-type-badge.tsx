import { cn } from "@/lib/utils";

const typeConfig: Record<
  string,
  { label: string; bg: string; text: string }
> = {
  success_pattern: {
    label: "Success Pattern",
    bg: "bg-emerald-500/15",
    text: "text-emerald-400",
  },
  comparative_insight: {
    label: "Comparative Insight",
    bg: "bg-sky-500/15",
    text: "text-sky-400",
  },
  root_cause: {
    label: "Root Cause",
    bg: "bg-rose-500/15",
    text: "text-rose-400",
  },
  general: {
    label: "General",
    bg: "bg-zinc-500/15",
    text: "text-zinc-400",
  },
};

interface LessonTypeBadgeProps {
  lessonType: string;
  className?: string;
}

export function LessonTypeBadge({ lessonType, className }: LessonTypeBadgeProps) {
  const config = typeConfig[lessonType] ?? {
    label: lessonType,
    bg: "bg-zinc-500/15",
    text: "text-zinc-400",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium",
        config.bg,
        config.text,
        className,
      )}
    >
      {config.label}
    </span>
  );
}
