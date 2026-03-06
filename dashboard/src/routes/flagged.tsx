import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/layout/page-header";

export const Route = createFileRoute("/flagged")({
  component: FlaggedPage,
});

function FlaggedPage() {
  return (
    <div>
      <PageHeader
        title="Flagged for Review"
        description="Lessons flagged due to accumulated failure penalties"
      />
      <p className="text-muted-foreground text-sm">Flagged lessons view coming soon.</p>
    </div>
  );
}
