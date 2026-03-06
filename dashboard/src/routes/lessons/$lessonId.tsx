import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/layout/page-header";

export const Route = createFileRoute("/lessons/$lessonId")({
  component: LessonDetailPage,
});

function LessonDetailPage() {
  const { lessonId } = Route.useParams();
  return (
    <div>
      <PageHeader title="Lesson Detail" />
      <p className="text-muted-foreground text-sm">Lesson {lessonId} — detail view coming soon.</p>
    </div>
  );
}
