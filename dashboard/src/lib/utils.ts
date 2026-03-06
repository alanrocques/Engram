import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Date formatters
export function formatDate(date: string | Date): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(date));
}

export function formatDateTime(date: string | Date): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(date));
}

export function formatRelative(date: string | Date): string {
  const now = new Date();
  const then = new Date(date);
  const diffMs = now.getTime() - then.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffSec < 60) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  if (diffDay < 7) return `${diffDay}d ago`;
  return formatDate(date);
}

// Utility score → color
export function utilityToColor(utility: number): {
  bg: string;
  text: string;
  label: string;
} {
  if (utility < 0.3) {
    return { bg: "bg-rose-500/20", text: "text-rose-400", label: "Low" };
  }
  if (utility < 0.7) {
    return { bg: "bg-amber-500/20", text: "text-amber-400", label: "Medium" };
  }
  return { bg: "bg-emerald-500/20", text: "text-emerald-400", label: "High" };
}

export function confidenceToColor(confidence: number): {
  bg: string;
  text: string;
} {
  if (confidence < 0.4) {
    return { bg: "bg-rose-500/20", text: "text-rose-400" };
  }
  if (confidence < 0.7) {
    return { bg: "bg-amber-500/20", text: "text-amber-400" };
  }
  return { bg: "bg-emerald-500/20", text: "text-emerald-400" };
}

export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength - 3) + "...";
}
