import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { FailureQueueStats } from "@/types/api";

const failureQueueKeys = {
  all: ["failure-queue"] as const,
  stats: () => [...failureQueueKeys.all, "stats"] as const,
};

export function useFailureQueueStats() {
  return useQuery({
    queryKey: failureQueueKeys.stats(),
    queryFn: () => api.get<FailureQueueStats>("/api/v1/failure-queue/stats"),
    refetchInterval: 60_000,
  });
}

export function useTriggerBatchAnalysis() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.post<{
        status: string;
        message: string;
        groups_processed?: number;
        lessons_created?: number;
      }>("/api/v1/failure-queue/analyze"),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: failureQueueKeys.all });
      if (data.status === "completed" && (data.lessons_created ?? 0) > 0) {
        void queryClient.invalidateQueries({ queryKey: ["lessons"] });
      }
    },
  });
}
