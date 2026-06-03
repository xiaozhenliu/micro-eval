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
      <h2 className="text-xl font-semibold mb-2">Run: {run.id}</h2>
      <p className="text-sm text-neutral-400 mb-6">
        {new Date(run.created_at).toLocaleString()} · {run.status} · {run.project_name}
      </p>

      <DecisionSummary run={run} />
      <CaveatBanner run={run} />

      <ComparisonTable tasks={run.tasks} configurations={run.configurations} results={run.results} />
      <CellDetail run={run} />
      <AnnotationPanel runId={run.id} cells={run.results} />
    </div>
  );
}
