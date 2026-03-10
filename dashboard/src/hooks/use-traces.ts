import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
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

export function useProcessTrace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post(`/api/v1/traces/${id}/process`),
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: traceKeys.detail(id) });
      void queryClient.invalidateQueries({ queryKey: traceKeys.lists() });
    },
  });
}

export function useDeleteTrace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/v1/traces/${id}`),
    onSuccess: () => {
      toast.success("Trace deleted");
      void queryClient.invalidateQueries({ queryKey: traceKeys.lists() });
    },
    onError: () => {
      toast.error("Failed to delete trace");
    },
  });
}

export function useDeleteTraces() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) =>
      api.post("/api/v1/traces/delete", { ids }),
    onSuccess: (_data, ids) => {
      toast.success(`Deleted ${ids.length} trace${ids.length === 1 ? "" : "s"}`);
      void queryClient.invalidateQueries({ queryKey: traceKeys.lists() });
    },
    onError: () => {
      toast.error("Failed to delete traces");
    },
  });
}
