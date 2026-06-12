import Link from "next/link";
import { notFound } from "next/navigation";
import { getRun } from "@/lib/api";
import { CaveatBanner } from "@/components/CaveatBanner";
import { CellDetail } from "@/components/CellDetail";
import { CostPanel } from "@/components/CostPanel";
import { DecisionSummary } from "@/components/DecisionSummary";
import { MatrixHeatmap } from "@/components/MatrixHeatmap";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function ReviewPage({ params }: PageProps) {
  const { id } = await params;
  const run = await getRun(id);
  if (!run) notFound();

  const strongWinnerHidden = run.decision?.verdict === "not_comparable" || run.decision?.verdict === "inconclusive";

  return (
    <div className="space-y-6">
      <div>
        <Link href={`/run/${run.id}`} className="text-sm text-blue-400 hover:underline">← Back to run</Link>
        <h2 className="mt-2 text-xl font-semibold">Review: {run.id}</h2>
        <p className="text-sm text-neutral-400">{new Date(run.created_at).toLocaleString()} · {run.status} · {run.project_name}</p>
        {strongWinnerHidden && (
          <p className="mt-2 rounded border border-amber-900/60 bg-amber-950/30 p-2 text-sm text-amber-200">
            No winner is shown because the run is {run.decision?.verdict ?? "inconclusive"}.
          </p>
        )}
      </div>
      <DecisionSummary run={run} />
      <CaveatBanner run={run} />
      <div className="grid gap-6 xl:grid-cols-[1.2fr_1fr]">
        <MatrixHeatmap runId={run.id} tasks={run.tasks} configurations={run.configurations} results={run.results} />
        <CostPanel decision={run.decision} />
      </div>
      <CellDetail run={run} />
    </div>
  );
}
