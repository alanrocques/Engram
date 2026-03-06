import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Trace, TraceFilters } from "@/types/api";

const traceKeys = {
  all: ["traces"] as const,
  lists: () => [...traceKeys.all, "list"] as const,
  list: (filters: TraceFilters) => [...traceKeys.lists(), filters] as const,
  detail: (id: string) => [...traceKeys.all, "detail", id] as const,
};

export function useTraces(filters: TraceFilters = {}) {
  return useQuery({
    queryKey: traceKeys.list(filters),
    queryFn: () =>
      api.get<Trace[]>("/api/v1/traces", {
        agent_id: filters.agent_id,
        status: filters.status,
        limit: filters.limit ?? 100,
        offset: filters.offset ?? 0,
      }),
  });
}

export function useTrace(id: string) {
  return useQuery({
    queryKey: traceKeys.detail(id),
    queryFn: () => api.get<Trace>(`/api/v1/traces/${id}`),
    enabled: Boolean(id),
  });
}
