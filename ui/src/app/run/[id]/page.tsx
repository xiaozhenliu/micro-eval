import { notFound } from "next/navigation";
import { getRun } from "@/lib/api";
import { CaveatBanner } from "@/components/CaveatBanner";
import { CellDetail } from "@/components/CellDetail";
import { ComparisonTable } from "@/components/ComparisonTable";
import { DecisionSummary } from "@/components/DecisionSummary";
import { AnnotationPanel } from "@/components/AnnotationPanel";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function RunPage({ params }: PageProps) {
  const { id } = await params;
  const run = await getRun(id);

  if (!run) {
    notFound();
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-4">
        <h2 className="text-xl font-semibold">Run: {run.id}</h2>
        <a className="text-sm text-blue-400 hover:underline" href={`/run/${run.id}/review`}>Open review</a>
      </div>
      <p className="text-sm text-neutral-400 mb-6">
        {new Date(run.created_at).toLocaleString()} · {run.status} · {run.project_name}
      </p>

      <DecisionSummary run={run} />
      <CaveatBanner run={run} />

      <ComparisonTable tasks={run.tasks} configurations={run.configurations} results={run.results} decision={run.decision} />
      <CellDetail run={run} />
      <AnnotationPanel runId={run.id} cells={run.results} />
    </div>
  );
}
