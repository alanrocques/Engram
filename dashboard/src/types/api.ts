import { z } from "zod";

// ---------------------------------------------------------------------------
// Primitives
// ---------------------------------------------------------------------------

const uuid = z.string().uuid();
const isoDate = z.string().datetime();

// ---------------------------------------------------------------------------
// Lesson
// ---------------------------------------------------------------------------

export const LessonSchema = z.object({
  id: uuid,
  agent_id: z.string(),
  task_context: z.string(),
  state_snapshot: z.record(z.string(), z.unknown()),
  action_taken: z.string(),
  outcome: z.enum(["success", "failure", "partial"]),
  lesson_text: z.string(),
  confidence: z.number(),
  created_at: isoDate,
  last_validated: isoDate.nullable(),
  tags: z.array(z.string()),
  source_trace_id: uuid.nullable(),
  version: z.number().int(),
  domain: z.string(),
  is_archived: z.boolean(),
  has_conflict: z.boolean(),
  conflict_ids: z.array(uuid),
  // Phase 2.5 — utility
  utility: z.number(),
  retrieval_count: z.number().int(),
  success_count: z.number().int(),
  last_retrieved_at: isoDate.nullable(),
  // Phase 2 — distillation
  lesson_type: z.string(),
  extraction_mode: z.string().nullable(),
  source_trace_ids: z.array(uuid).nullable(),
  // Phase 3 — provenance
  parent_lesson_ids: z.array(uuid),
  child_lesson_ids: z.array(uuid),
  propagation_penalty: z.number(),
  needs_review: z.boolean(),
  review_reason: z.string().nullable(),
});

export type Lesson = z.infer<typeof LessonSchema>;

// ---------------------------------------------------------------------------
// Trace
// ---------------------------------------------------------------------------

export const TraceSchema = z.object({
  id: uuid,
  agent_id: z.string(),
  span_count: z.number().int(),
  status: z.enum(["pending", "processed", "failed"]),
  created_at: isoDate,
  processed_at: isoDate.nullable(),
  content_hash: z.string().nullable(),
  outcome: z.string().nullable(),
  extraction_mode: z.string().nullable(),
  retrieved_lesson_ids: z.array(uuid).nullable(),
  is_influenced: z.boolean().optional(),
  trace_data: z.record(z.string(), z.unknown()).nullable().optional(),
});

export type Trace = z.infer<typeof TraceSchema>;

// ---------------------------------------------------------------------------
// LessonRetrieval
// ---------------------------------------------------------------------------

export const LessonRetrievalSchema = z.object({
  id: uuid,
  lesson_id: uuid,
  trace_id: uuid.nullable(),
  retrieved_at: isoDate,
  outcome: z.string().nullable(),
  outcome_reported_at: isoDate.nullable(),
  reward: z.number().nullable(),
  context_similarity: z.number().nullable(),
});

export type LessonRetrieval = z.infer<typeof LessonRetrievalSchema>;

// ---------------------------------------------------------------------------
// ProvenanceEvent
// ---------------------------------------------------------------------------

export const ProvenanceEventSchema = z.object({
  id: z.string(),
  event_type: z.string(),
  trace_id: z.string().nullable(),
  related_lesson_id: z.string().nullable(),
  payload: z.record(z.string(), z.unknown()).nullable(),
  created_at: z.string(),
});

export type ProvenanceEvent = z.infer<typeof ProvenanceEventSchema>;

export const ProvenanceResponseSchema = z.object({
  lesson_id: z.string(),
  parent_lesson_ids: z.array(z.string()),
  child_lesson_ids: z.array(z.string()),
  propagation_penalty: z.number(),
  needs_review: z.boolean(),
  review_reason: z.string().nullable(),
  retrieval_history: z.array(
    z.object({
      id: z.string(),
      trace_id: z.string().nullable(),
      retrieved_at: z.string().nullable(),
      outcome: z.string().nullable(),
      reward: z.number().nullable(),
    }),
  ),
  provenance_events: z.array(ProvenanceEventSchema),
});

export type ProvenanceResponse = z.infer<typeof ProvenanceResponseSchema>;

// ---------------------------------------------------------------------------
// FailureQueueStats
// ---------------------------------------------------------------------------

export const FailureQueueStatsSchema = z.object({
  pending: z.number().int(),
  by_category: z.record(z.string(), z.number()),
  by_signature: z.record(z.string(), z.number()),
});

export type FailureQueueStats = z.infer<typeof FailureQueueStatsSchema>;

// ---------------------------------------------------------------------------
// OverviewStats (derived client-side from multiple endpoints)
// ---------------------------------------------------------------------------

export const OverviewStatsSchema = z.object({
  total_lessons: z.number().int(),
  total_traces: z.number().int(),
  lessons_by_outcome: z.object({
    success: z.number().int(),
    failure: z.number().int(),
    partial: z.number().int(),
  }),
  avg_confidence: z.number(),
  avg_utility: z.number(),
  flagged_count: z.number().int(),
  conflict_count: z.number().int(),
  archived_count: z.number().int(),
  failure_queue_pending: z.number().int(),
});

export type OverviewStats = z.infer<typeof OverviewStatsSchema>;

// ---------------------------------------------------------------------------
// Paginated wrapper
// ---------------------------------------------------------------------------

export function paginatedSchema<T extends z.ZodTypeAny>(itemSchema: T) {
  return z.object({
    items: z.array(itemSchema),
    total: z.number().int(),
    offset: z.number().int(),
    limit: z.number().int(),
  });
}

export type PaginatedResponse<T> = {
  items: T[];
  total: number;
  offset: number;
  limit: number;
};

// ---------------------------------------------------------------------------
// Filter params
// ---------------------------------------------------------------------------

export interface LessonFilters {
  agent_id?: string;
  domain?: string;
  outcome?: string;
  min_confidence?: number;
  include_archived?: boolean;
  limit?: number;
  offset?: number;
}

export interface TraceFilters {
  agent_id?: string;
  status?: string;
  limit?: number;
  offset?: number;
}
