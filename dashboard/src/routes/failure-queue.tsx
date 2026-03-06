import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/layout/page-header";

export const Route = createFileRoute("/failure-queue")({
  component: FailureQueuePage,
});

function FailureQueuePage() {
  return (
    <div>
      <PageHeader
        title="Failure Queue"
        description="Grouped failure traces awaiting batch analysis"
      />
      <p className="text-muted-foreground text-sm">Failure queue view coming soon.</p>
    </div>
  );
}
