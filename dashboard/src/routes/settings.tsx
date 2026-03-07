import type { ReactNode } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/layout/page-header";
import { api } from "@/lib/api";

export const Route = createFileRoute("/settings")({
  component: SettingsPage,
});

interface ConfigResponse {
  extraction_model: string;
  embedding_model: string;
  embedding_dim: number;
  lesson_confidence_half_life_days: number;
  max_lessons_per_retrieval: number;
  min_confidence_threshold: number;
  otel_grpc_port: number;
  otel_http_port: number;
}

function useConfig() {
  return useQuery({
    queryKey: ["config"],
    queryFn: () => api.get<ConfigResponse>("/api/v1/config"),
  });
}

function ConfigSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900">
      <div className="border-b border-zinc-800 px-4 py-3">
        <h2 className="text-sm font-medium text-zinc-100">{title}</h2>
      </div>
      <div className="divide-y divide-zinc-800">{children}</div>
    </div>
  );
}

function ConfigRow({
  name,
  value,
  description,
}: {
  name: string;
  value: string | number;
  description: string;
}) {
  return (
    <div className="flex items-start justify-between gap-4 px-4 py-3">
      <div>
        <p className="text-sm font-mono text-zinc-300">{name}</p>
        <p className="mt-0.5 text-xs text-zinc-500">{description}</p>
      </div>
      <div className="shrink-0 text-sm font-mono text-blue-400">{String(value)}</div>
    </div>
  );
}

function ConfigSectionSkeleton({ rows }: { rows: number }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900">
      <div className="border-b border-zinc-800 px-4 py-3">
        <div className="h-4 w-32 animate-pulse rounded bg-zinc-800" />
      </div>
      <div className="divide-y divide-zinc-800">
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="flex items-start justify-between gap-4 px-4 py-3">
            <div className="flex-1">
              <div className="h-4 w-48 animate-pulse rounded bg-zinc-800" />
              <div className="mt-1.5 h-3 w-72 animate-pulse rounded bg-zinc-800" />
            </div>
            <div className="h-4 w-20 animate-pulse rounded bg-zinc-800" />
          </div>
        ))}
      </div>
    </div>
  );
}

function SettingsPage() {
  const { data: config, isLoading, isError } = useConfig();

  return (
    <div>
      <PageHeader
        title="Settings"
        description="System configuration — read-only display"
      />

      {isError && (
        <p className="text-sm text-rose-400">Failed to load configuration</p>
      )}

      {isLoading ? (
        <div className="space-y-6">
          <ConfigSectionSkeleton rows={3} />
          <ConfigSectionSkeleton rows={3} />
          <ConfigSectionSkeleton rows={2} />
        </div>
      ) : config ? (
        <div className="space-y-6">
          <ConfigSection title="Learning & Memory">
            <ConfigRow
              name="lesson_confidence_half_life_days"
              value={config.lesson_confidence_half_life_days}
              description="Days until lesson confidence decays to 50% of its original value. Higher = lessons stay relevant longer."
            />
            <ConfigRow
              name="max_lessons_per_retrieval"
              value={config.max_lessons_per_retrieval}
              description="Maximum number of lessons returned per retrieval request."
            />
            <ConfigRow
              name="min_confidence_threshold"
              value={config.min_confidence_threshold}
              description="Lessons below this confidence are auto-archived during decay runs."
            />
          </ConfigSection>

          <ConfigSection title="Models">
            <ConfigRow
              name="extraction_model"
              value={config.extraction_model}
              description="Claude model used for lesson extraction from traces."
            />
            <ConfigRow
              name="embedding_model"
              value={config.embedding_model}
              description="Sentence transformer model for generating lesson embeddings."
            />
            <ConfigRow
              name="embedding_dim"
              value={config.embedding_dim}
              description="Dimensionality of lesson embedding vectors."
            />
          </ConfigSection>

          <ConfigSection title="OpenTelemetry">
            <ConfigRow
              name="otel_grpc_port"
              value={config.otel_grpc_port}
              description="Port for OTLP/gRPC trace ingestion."
            />
            <ConfigRow
              name="otel_http_port"
              value={config.otel_http_port}
              description="Port for OTLP/HTTP trace ingestion."
            />
          </ConfigSection>
        </div>
      ) : null}
    </div>
  );
}
