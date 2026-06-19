import Link from "next/link";
import { notFound } from "next/navigation";
import fs from "node:fs";
import path from "node:path";
import { getWorkspaceRunsDir } from "@/lib/workspace-api";
import { RunSchema, DecisionReportSchema } from "@/lib/schema";
import type { Run } from "@/lib/schema";
import { CaveatBanner } from "@/components/CaveatBanner";
import { CellDetail } from "@/components/CellDetail";
import { CostPanel } from "@/components/CostPanel";
import { DecisionSummary } from "@/components/DecisionSummary";
import { MatrixHeatmap } from "@/components/MatrixHeatmap";

interface PageProps {
  params: Promise<{ id: string; runId: string }>;
}

function safeRunId(id: string): string | null {
  return /^[A-Za-z0-9_.:-]+$/.test(id) ? id : null;
}

function loadWorkspaceRun(workspaceId: string, runId: string): Run | null {
  const safe = safeRunId(runId);
  if (!safe) return null;

  const runsDir = getWorkspaceRunsDir(workspaceId);
  if (!runsDir) return null;

  const runDir = path.join(runsDir, safe);
  const runFile = path.join(runDir, "run.json");
  if (!fs.existsSync(runFile)) return null;

  try {
    const run = RunSchema.parse(JSON.parse(fs.readFileSync(runFile, "utf-8")));
    const decisionFile = path.join(runDir, "decision.json");
    if (fs.existsSync(decisionFile)) {
      const decision = DecisionReportSchema.parse(JSON.parse(fs.readFileSync(decisionFile, "utf-8")));
      return { ...run, decision };
    }
    return run;
  } catch {
    return null;
  }
}

export default async function WorkspaceRunReviewPage({ params }: PageProps) {
  const { id, runId } = await params;
  const run = loadWorkspaceRun(id, runId);
  if (!run) notFound();

  const strongWinnerHidden =
    run.decision?.verdict === "not_comparable" || run.decision?.verdict === "inconclusive";

  return (
    <div className="space-y-6">
      <div>
        <Link href={`/workspace/${id}/run/${run.id}`} className="text-sm text-blue-400 hover:underline">
          ← Back to run
        </Link>
        <h2 className="mt-2 text-xl font-semibold">Review: {run.id}</h2>
        <p className="text-sm text-neutral-400">
          {new Date(run.created_at).toLocaleString()} · {run.status} · {run.project_name}
        </p>
        {strongWinnerHidden && (
          <p className="mt-2 rounded border border-amber-900/60 bg-amber-950/30 p-2 text-sm text-amber-200">
            No winner is shown because the run is {run.decision?.verdict ?? "inconclusive"}.
          </p>
        )}
      </div>

      <DecisionSummary run={run} />
      <CaveatBanner run={run} />

      <div className="grid gap-6 xl:grid-cols-[1.2fr_1fr]">
        <MatrixHeatmap
          runId={run.id}
          tasks={run.tasks}
          configurations={run.configurations}
          results={run.results}
        />
        <CostPanel decision={run.decision} />
      </div>
      <CellDetail run={run} />
    </div>
  );
}
