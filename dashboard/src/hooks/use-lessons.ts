import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Lesson, LessonFilters, ProvenanceResponse } from "@/types/api";

const lessonKeys = {
  all: ["lessons"] as const,
  lists: () => [...lessonKeys.all, "list"] as const,
  list: (filters: LessonFilters) => [...lessonKeys.lists(), filters] as const,
  details: () => [...lessonKeys.all, "detail"] as const,
  detail: (id: string) => [...lessonKeys.details(), id] as const,
  provenance: (id: string) => [...lessonKeys.all, "provenance", id] as const,
  flagged: () => [...lessonKeys.all, "flagged"] as const,
  conflicts: () => [...lessonKeys.all, "conflicts"] as const,
};

export function useLessons(filters: LessonFilters = {}) {
  return useQuery({
    queryKey: lessonKeys.list(filters),
    queryFn: () =>
      api.get<Lesson[]>("/api/v1/lessons", {
        agent_id: filters.agent_id,
        domain: filters.domain,
        outcome: filters.outcome,
        min_confidence: filters.min_confidence,
        include_archived: filters.include_archived,
        limit: filters.limit ?? 100,
        offset: filters.offset ?? 0,
      }),
  });
}

export function useLesson(id: string) {
  return useQuery({
    queryKey: lessonKeys.detail(id),
    queryFn: () => api.get<Lesson>(`/api/v1/lessons/${id}`),
    enabled: Boolean(id),
  });
}

export function useLessonProvenance(id: string) {
  return useQuery({
    queryKey: lessonKeys.provenance(id),
    queryFn: () => api.get<ProvenanceResponse>(`/api/v1/lessons/${id}/provenance`),
    enabled: Boolean(id),
  });
}

export function useFlaggedLessons() {
  return useQuery({
    queryKey: lessonKeys.flagged(),
    queryFn: () => api.get<Lesson[]>("/api/v1/lessons/flagged"),
  });
}

export function useConflictingLessons() {
  return useQuery({
    queryKey: lessonKeys.conflicts(),
    queryFn: () =>
      api.get<{ conflicts: Lesson[]; total: number }>("/api/v1/lessons/conflicts"),
  });
}

export function useArchiveLesson() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.patch<Lesson>(`/api/v1/lessons/${id}`, { is_archived: true }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: lessonKeys.all });
    },
  });
}

export function useMarkReviewed() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.patch<Lesson>(`/api/v1/lessons/${id}`, { needs_review: false }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: lessonKeys.all });
    },
  });
}

export function useUpdateLesson() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Lesson> }) =>
      api.patch<Lesson>(`/api/v1/lessons/${id}`, data),
    onSuccess: (_data, { id }) => {
      void queryClient.invalidateQueries({ queryKey: lessonKeys.detail(id) });
      void queryClient.invalidateQueries({ queryKey: lessonKeys.lists() });
    },
  });
}
