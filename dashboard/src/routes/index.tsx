import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/layout/page-header";

export const Route = createFileRoute("/")({
  component: OverviewPage,
});

function OverviewPage() {
  return (
    <div>
      <PageHeader
        title="Overview"
        description="System-wide memory health and activity"
      />
      <p className="text-muted-foreground text-sm">Dashboard coming soon.</p>
    </div>
  );
}
