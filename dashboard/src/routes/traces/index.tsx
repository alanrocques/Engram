import { Fragment, useMemo, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  getFilteredRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
  type ExpandedState,
} from "@tanstack/react-table";
import { ChevronDown, ChevronRight, ChevronUp, Inbox, Zap } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { useTraces } from "@/hooks/use-traces";
import { cn, formatRelative } from "@/lib/utils";
import type { Trace } from "@/types/api";

export const Route = createFileRoute("/traces/")({
  component: TracesPage,
});

const outcomeBadgeColor: Record<string, string> = {
  success: "bg-emerald-500/15 text-emerald-400",
  failure: "bg-rose-500/15 text-rose-400",
  partial: "bg-amber-500/15 text-amber-400",
};

const statusBadgeColor: Record<string, string> = {
  pending: "bg-amber-500/15 text-amber-400",
  processed: "bg-emerald-500/15 text-emerald-400",
  failed: "bg-rose-500/15 text-rose-400",
};

const columns: ColumnDef<Trace, unknown>[] = [
  {
    id: "expand",
    header: "",
    cell: ({ row }) =>
      row.getCanExpand() ? (
        <button
          onClick={(e) => {
            e.stopPropagation();
            row.toggleExpanded();
          }}
          className="text-zinc-400 hover:text-zinc-200"
        >
          {row.getIsExpanded() ? (
            <ChevronDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
        </button>
      ) : null,
    size: 36,
    enableSorting: false,
  },
  {
    accessorKey: "id",
    header: "ID",
    cell: ({ row }) => (
      <Link
        to="/traces/$traceId"
        params={{ traceId: row.original.id }}
        onClick={(e: React.MouseEvent) => e.stopPropagation()}
        className="font-mono text-xs text-blue-400 hover:text-blue-300 hover:underline"
      >
        {row.original.id.slice(0, 8)}
      </Link>
    ),
    size: 90,
  },
  {
    accessorKey: "agent_id",
    header: "Agent",
    cell: ({ row }) => (
      <span className="text-zinc-200">{row.original.agent_id}</span>
    ),
    size: 150,
  },
  {
    accessorKey: "outcome",
    header: "Outcome",
    cell: ({ row }) => {
      const outcome = row.original.outcome;
      if (!outcome) {
        return (
          <span className="inline-flex items-center rounded-md bg-zinc-500/15 px-2 py-0.5 text-xs font-medium text-zinc-400">
            pending
          </span>
        );
      }
      return (
        <span
          className={cn(
            "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium",
            outcomeBadgeColor[outcome] ?? "bg-zinc-500/15 text-zinc-400",
          )}
        >
          {outcome}
        </span>
      );
    },
    size: 100,
  },
  {
    accessorKey: "is_influenced",
    header: "Memory",
    cell: ({ row }) =>
      row.original.is_influenced ? (
        <div title="Influenced by memory">
          <Zap className="h-3.5 w-3.5 text-blue-400" />
        </div>
      ) : null,
    size: 70,
  },
  {
    accessorKey: "extraction_mode",
    header: "Extraction",
    cell: ({ row }) => (
      <span className="text-zinc-400">
        {row.original.extraction_mode ?? "-"}
      </span>
    ),
    size: 120,
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => (
      <span
        className={cn(
          "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium",
          statusBadgeColor[row.original.status] ?? "bg-zinc-500/15 text-zinc-400",
        )}
      >
        {row.original.status}
      </span>
    ),
    size: 100,
  },
  {
    accessorKey: "created_at",
    header: "Created",
    cell: ({ row }) => (
      <span className="text-zinc-400">{formatRelative(row.original.created_at)}</span>
    ),
    size: 100,
  },
];

function TracesPage() {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [expanded, setExpanded] = useState<ExpandedState>({});

  // Filters
  const [outcomeFilter, setOutcomeFilter] = useState("all");
  const [agentFilter, setAgentFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [influencedOnly, setInfluencedOnly] = useState(false);

  const { data, isLoading } = useTraces({ limit: 500 });

  const filteredData = useMemo(() => {
    if (!data) return [];
    let result = data;
    if (outcomeFilter !== "all") {
      result = result.filter((t) => t.outcome === outcomeFilter);
    }
    if (agentFilter) {
      const q = agentFilter.toLowerCase();
      result = result.filter((t) => t.agent_id.toLowerCase().includes(q));
    }
    if (statusFilter !== "all") {
      result = result.filter((t) => t.status === statusFilter);
    }
    if (influencedOnly) {
      result = result.filter((t) => t.is_influenced);
    }
    return result;
  }, [data, outcomeFilter, agentFilter, statusFilter, influencedOnly]);

  const table = useReactTable({
    data: filteredData,
    columns,
    state: { sorting, expanded },
    onSortingChange: setSorting,
    onExpandedChange: setExpanded,
    getRowCanExpand: () => true,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    initialState: { pagination: { pageSize: 50 } },
  });

  return (
    <div>
      <PageHeader
        title="Traces"
        description="View ingested agent execution traces"
      />

      <div className="rounded-lg border border-zinc-800 bg-zinc-900">
        {/* Filter bar */}
        <div className="flex flex-wrap items-center gap-3 border-b border-zinc-800 p-4">
          <select
            value={outcomeFilter}
            onChange={(e) => { setOutcomeFilter(e.target.value); setExpanded({}); }}
            className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-sm text-zinc-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="all">All outcomes</option>
            <option value="success">Success</option>
            <option value="failure">Failure</option>
            <option value="partial">Partial</option>
          </select>

          <input
            type="text"
            placeholder="Filter by agent ID..."
            value={agentFilter}
            onChange={(e) => { setAgentFilter(e.target.value); setExpanded({}); }}
            className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-sm text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />

          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setExpanded({}); }}
            className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-sm text-zinc-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="all">All statuses</option>
            <option value="pending">Pending</option>
            <option value="processed">Processed</option>
            <option value="failed">Failed</option>
          </select>

          <label className="flex items-center gap-1.5 text-xs text-zinc-400">
            <input
              type="checkbox"
              checked={influencedOnly}
              onChange={(e) => { setInfluencedOnly(e.target.checked); setExpanded({}); }}
              className="accent-blue-500"
            />
            Influenced only
          </label>
        </div>

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
                      <Inbox className="h-8 w-8" />
                      <span>No traces found</span>
                    </div>
                  </td>
                </tr>
              )}

              {table.getRowModel().rows.map((row) => (
                <Fragment key={row.id}>
                  <tr
                    onClick={() => row.toggleExpanded()}
                    className="cursor-pointer border-b border-zinc-800/50 hover:bg-zinc-800/50"
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-3 py-2.5">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                  {row.getIsExpanded() && (
                    <tr key={`${row.id}-expanded`} className="border-b border-zinc-800/50">
                      <td colSpan={columns.length} className="bg-zinc-800/30 px-6 py-4">
                        <div className="space-y-2 text-sm">
                          <div>
                            <span className="text-zinc-500">Full ID: </span>
                            <span className="font-mono text-xs text-zinc-300">
                              {row.original.id}
                            </span>
                          </div>
                          <div>
                            <span className="text-zinc-500">Spans: </span>
                            <span className="text-zinc-300">{row.original.span_count}</span>
                          </div>
                          {row.original.content_hash && (
                            <div>
                              <span className="text-zinc-500">Content hash: </span>
                              <span className="font-mono text-xs text-zinc-400">
                                {row.original.content_hash}
                              </span>
                            </div>
                          )}
                          {row.original.retrieved_lesson_ids &&
                            row.original.retrieved_lesson_ids.length > 0 && (
                              <div>
                                <span className="text-zinc-500">Retrieved lessons: </span>
                                <div className="mt-1 flex flex-wrap gap-1">
                                  {row.original.retrieved_lesson_ids.map((lid) => (
                                    <Link
                                      key={lid}
                                      to="/lessons/$lessonId"
                                      params={{ lessonId: lid }}
                                      onClick={(e: React.MouseEvent) => e.stopPropagation()}
                                      className="rounded bg-blue-500/15 px-2 py-0.5 font-mono text-xs text-blue-400 hover:bg-blue-500/25"
                                    >
                                      {lid.slice(0, 8)}
                                    </Link>
                                  ))}
                                </div>
                              </div>
                            )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
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
