import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/layout/page-header";

export const Route = createFileRoute("/settings")({
  component: SettingsPage,
});

function SettingsPage() {
  return (
    <div>
      <PageHeader
        title="Settings"
        description="Agent configurations and decay policies"
      />
      <p className="text-muted-foreground text-sm">Settings coming soon.</p>
    </div>
  );
}
