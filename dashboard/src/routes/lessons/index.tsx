import { useState, useMemo } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  getFilteredRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
  type RowSelectionState,
} from "@tanstack/react-table";
import { AlertTriangle, BookOpen, ChevronDown, ChevronUp, Flag } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/page-header";
import { UtilityBadge } from "@/components/lessons/utility-badge";
import { LessonTypeBadge } from "@/components/lessons/lesson-type-badge";
import { useLessons, useArchiveLesson, useUpdateLesson } from "@/hooks/use-lessons";
import { cn, formatRelative, truncate, confidenceToColor } from "@/lib/utils";
import type { Lesson } from "@/types/api";

export const Route = createFileRoute("/lessons/")({
  component: LessonsPage,
});

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

const columns: ColumnDef<Lesson, unknown>[] = [
  {
    id: "select",
    header: ({ table }) => (
      <input
        type="checkbox"
        className="accent-blue-500"
        checked={table.getIsAllPageRowsSelected()}
        onChange={table.getToggleAllPageRowsSelectedHandler()}
      />
    ),
    cell: ({ row }) => (
      <input
        type="checkbox"
        className="accent-blue-500"
        checked={row.getIsSelected()}
        onChange={row.getToggleSelectedHandler()}
        onClick={(e) => e.stopPropagation()}
      />
    ),
    enableSorting: false,
    size: 40,
  },
  {
    accessorKey: "lesson_text",
    header: "Content",
    cell: ({ row }) => (
      <span className="text-zinc-200">{truncate(row.original.lesson_text, 100)}</span>
    ),
    size: 360,
  },
  {
    accessorKey: "lesson_type",
    header: "Type",
    cell: ({ row }) => <LessonTypeBadge lessonType={row.original.lesson_type} />,
    size: 150,
  },
  {
    accessorKey: "utility",
    header: "Utility",
    cell: ({ row }) => <UtilityBadge utility={row.original.utility} showBar />,
    size: 180,
  },
  {
    accessorKey: "confidence",
    header: "Confidence",
    cell: ({ row }) => <ConfidenceBar confidence={row.original.confidence} />,
    size: 150,
  },
  {
    accessorKey: "retrieval_count",
    header: "Retrievals",
    cell: ({ row }) => (
      <span className="tabular-nums text-zinc-300">{row.original.retrieval_count}</span>
    ),
    meta: { align: "right" },
    size: 90,
  },
  {
    accessorKey: "success_count",
    header: "Successes",
    cell: ({ row }) => (
      <span className="tabular-nums text-zinc-300">{row.original.success_count}</span>
    ),
    meta: { align: "right" },
    size: 90,
  },
  {
    accessorKey: "propagation_penalty",
    header: "Penalty",
    cell: ({ row }) => {
      const penalty = row.original.propagation_penalty;
      return (
        <div className="flex items-center gap-1">
          {penalty > 0.3 && (
            <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
          )}
          <span className={cn("tabular-nums text-zinc-300", penalty > 0.3 && "text-amber-400")}>
            {penalty.toFixed(2)}
          </span>
        </div>
      );
    },
    size: 90,
  },
  {
    accessorKey: "created_at",
    header: "Created",
    cell: ({ row }) => (
      <span className="text-zinc-400">{formatRelative(row.original.created_at)}</span>
    ),
    size: 100,
  },
  {
    accessorKey: "needs_review",
    header: "Review",
    cell: ({ row }) =>
      row.original.needs_review ? (
        <Flag className="h-3.5 w-3.5 text-amber-500" />
      ) : null,
    size: 60,
  },
];

type LessonTypeFilter = "success_pattern" | "root_cause" | "comparative_insight" | "general";
const LESSON_TYPES: LessonTypeFilter[] = [
  "success_pattern",
  "root_cause",
  "comparative_insight",
  "general",
];

function LessonsPage() {
  const navigate = useNavigate();
  const [sorting, setSorting] = useState<SortingState>([]);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [globalFilter, setGlobalFilter] = useState("");

  // Filter state
  const [selectedTypes, setSelectedTypes] = useState<Set<LessonTypeFilter>>(new Set());
  const [outcomeFilter, setOutcomeFilter] = useState<string>("all");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [needsReviewOnly, setNeedsReviewOnly] = useState(false);
  const [minUtility, setMinUtility] = useState(0);
  const [minConfidence, setMinConfidence] = useState(0);

  const { data, isLoading } = useLessons({
    include_archived: includeArchived,
    limit: 500,
  });

  const archiveMutation = useArchiveLesson();
  const updateMutation = useUpdateLesson();

  const filteredData = useMemo(() => {
    if (!data) return [];
    let result = data;

    if (selectedTypes.size > 0) {
      result = result.filter((l) => selectedTypes.has(l.lesson_type as LessonTypeFilter));
    }
    if (outcomeFilter !== "all") {
      result = result.filter((l) => l.outcome === outcomeFilter);
    }
    if (needsReviewOnly) {
      result = result.filter((l) => l.needs_review);
    }
    if (minUtility > 0) {
      result = result.filter((l) => l.utility >= minUtility);
    }
    if (minConfidence > 0) {
      result = result.filter((l) => l.confidence >= minConfidence);
    }
    if (globalFilter) {
      const q = globalFilter.toLowerCase();
      result = result.filter(
        (l) =>
          l.lesson_text.toLowerCase().includes(q) ||
          l.task_context.toLowerCase().includes(q),
      );
    }
    return result;
  }, [data, selectedTypes, outcomeFilter, needsReviewOnly, minUtility, minConfidence, globalFilter]);

  const table = useReactTable({
    data: filteredData,
    columns,
    state: { sorting, rowSelection },
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    initialState: { pagination: { pageSize: 50 } },
  });

  const selectedCount = Object.keys(rowSelection).length;

  function handleBulkArchive(archive: boolean) {
    const selectedRows = table.getSelectedRowModel().rows;
    for (const row of selectedRows) {
      if (archive) {
        archiveMutation.mutate(row.original.id, {
          onSuccess: () => toast.success(`Lesson archived`),
        });
      } else {
        updateMutation.mutate(
          { id: row.original.id, data: { is_archived: false } },
          { onSuccess: () => toast.success(`Lesson unarchived`) },
        );
      }
    }
    setRowSelection({});
  }

  function toggleType(t: LessonTypeFilter) {
    setSelectedTypes((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  }

  return (
    <div>
      <PageHeader
        title="Lessons"
        description="Browse, search, and filter extracted lessons"
      />

      <div className="rounded-lg border border-zinc-800 bg-zinc-900">
        {/* Filter bar */}
        <div className="flex flex-wrap items-center gap-3 border-b border-zinc-800 p-4">
          <input
            type="text"
            placeholder="Search lessons..."
            value={globalFilter}
            onChange={(e) => setGlobalFilter(e.target.value)}
            className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-sm text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />

          <div className="flex items-center gap-1">
            {LESSON_TYPES.map((t) => (
              <button
                key={t}
                onClick={() => toggleType(t)}
                className={cn(
                  "rounded px-2 py-1 text-xs font-medium transition-colors",
                  selectedTypes.has(t)
                    ? "bg-blue-500/20 text-blue-400"
                    : "bg-zinc-800 text-zinc-400 hover:text-zinc-200",
                )}
              >
                {t.replace("_", " ")}
              </button>
            ))}
          </div>

          <select
            value={outcomeFilter}
            onChange={(e) => setOutcomeFilter(e.target.value)}
            className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-sm text-zinc-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="all">All outcomes</option>
            <option value="success">Success</option>
            <option value="failure">Failure</option>
            <option value="partial">Partial</option>
          </select>

          <label className="flex items-center gap-1.5 text-xs text-zinc-400">
            <input
              type="checkbox"
              checked={includeArchived}
              onChange={(e) => setIncludeArchived(e.target.checked)}
              className="accent-blue-500"
            />
            Include archived
          </label>

          <label className="flex items-center gap-1.5 text-xs text-zinc-400">
            <input
              type="checkbox"
              checked={needsReviewOnly}
              onChange={(e) => setNeedsReviewOnly(e.target.checked)}
              className="accent-blue-500"
            />
            Needs review only
          </label>

          <div className="flex items-center gap-1.5 text-xs text-zinc-400">
            <span>Utility &ge;</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.1}
              value={minUtility}
              onChange={(e) => setMinUtility(Number(e.target.value))}
              className="h-1 w-20 accent-blue-500"
            />
            <span className="tabular-nums text-zinc-300">{minUtility.toFixed(1)}</span>
          </div>

          <div className="flex items-center gap-1.5 text-xs text-zinc-400">
            <span>Conf &ge;</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.1}
              value={minConfidence}
              onChange={(e) => setMinConfidence(Number(e.target.value))}
              className="h-1 w-20 accent-blue-500"
            />
            <span className="tabular-nums text-zinc-300">{minConfidence.toFixed(1)}</span>
          </div>
        </div>

        {/* Bulk action bar */}
        {selectedCount > 0 && (
          <div className="flex items-center gap-3 border-b border-zinc-800 bg-zinc-800/50 px-4 py-2 text-sm">
            <span className="text-zinc-300">{selectedCount} selected</span>
            <button
              onClick={() => handleBulkArchive(true)}
              className="rounded bg-rose-500/15 px-2 py-0.5 text-xs font-medium text-rose-400 hover:bg-rose-500/25"
            >
              Archive
            </button>
            <button
              onClick={() => handleBulkArchive(false)}
              className="rounded bg-emerald-500/15 px-2 py-0.5 text-xs font-medium text-emerald-400 hover:bg-emerald-500/25"
            >
              Unarchive
            </button>
            <button
              onClick={() => setRowSelection({})}
              className="text-xs text-zinc-400 hover:text-zinc-200"
            >
              Clear selection
            </button>
          </div>
        )}

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 border-b border-zinc-800 bg-zinc-900">
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <th
                      key={header.id}
                      className={cn(
                        "px-3 py-2 text-left text-xs font-medium text-zinc-400",
                        header.column.getCanSort() && "cursor-pointer select-none hover:text-zinc-200",
                      )}
                      style={{ width: header.getSize() }}
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      <div className="flex items-center gap-1">
                        {header.isPlaceholder
                          ? null
                          : flexRender(header.column.columnDef.header, header.getContext())}
                        {header.column.getIsSorted() === "asc" && (
                          <ChevronUp className="h-3 w-3" />
                        )}
                        {header.column.getIsSorted() === "desc" && (
                          <ChevronDown className="h-3 w-3" />
                        )}
                      </div>
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {isLoading &&
                Array.from({ length: 10 }).map((_, i) => (
                  <tr key={`skeleton-${i}`} className="border-b border-zinc-800/50">
                    {columns.map((_, ci) => (
                      <td key={ci} className="px-3 py-3">
                        <div className="h-4 animate-pulse rounded bg-zinc-800" />
                      </td>
                    ))}
                  </tr>
                ))}

              {!isLoading && table.getRowModel().rows.length === 0 && (
                <tr>
                  <td colSpan={columns.length} className="py-16 text-center">
                    <div className="flex flex-col items-center gap-2 text-zinc-500">
                      <BookOpen className="h-8 w-8" />
                      <span>No lessons found</span>
                    </div>
                  </td>
                </tr>
              )}

              {table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  onClick={() =>
                    void navigate({
                      to: "/lessons/$lessonId",
                      params: { lessonId: row.original.id },
                    })
                  }
                  className={cn(
                    "cursor-pointer border-b border-zinc-800/50 hover:bg-zinc-800/50",
                    row.original.needs_review && "border-l-2 border-l-amber-500",
                  )}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-3 py-2.5">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {!isLoading && filteredData.length > 0 && (
          <div className="flex items-center justify-between border-t border-zinc-800 px-4 py-3 text-sm text-zinc-400">
            <div className="flex items-center gap-2">
              <span>Rows per page:</span>
              <select
                value={table.getState().pagination.pageSize}
                onChange={(e) => table.setPageSize(Number(e.target.value))}
                className="rounded border border-zinc-700 bg-zinc-800 px-1 py-0.5 text-xs text-zinc-100"
              >
                {[25, 50, 100].map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-3">
              <span className="tabular-nums">
                Page {table.getState().pagination.pageIndex + 1} of{" "}
                {table.getPageCount()}
              </span>
              <div className="flex gap-1">
                <button
                  onClick={() => table.previousPage()}
                  disabled={!table.getCanPreviousPage()}
                  className="rounded border border-zinc-700 bg-zinc-800 px-2 py-0.5 text-xs disabled:opacity-40"
                >
                  Prev
                </button>
                <button
                  onClick={() => table.nextPage()}
                  disabled={!table.getCanNextPage()}
                  className="rounded border border-zinc-700 bg-zinc-800 px-2 py-0.5 text-xs disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
