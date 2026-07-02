import Link from "next/link";
import { notFound } from "next/navigation";
import fs from "node:fs";
import path from "node:path";
import { getWorkspaceRunsDir } from "@/lib/workspace-api";
import { RunSchema, DecisionReportSchema } from "@/lib/schema";
import type { Run } from "@/lib/schema";
import { CaveatBanner } from "@/components/CaveatBanner";
import { CellDetail } from "@/components/CellDetail";
import { ComparisonTable } from "@/components/ComparisonTable";
import { DecisionSummary } from "@/components/DecisionSummary";
import { AnnotationPanel } from "@/components/AnnotationPanel";

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

export default async function WorkspaceRunPage({ params }: PageProps) {
  const { id, runId } = await params;
  const run = loadWorkspaceRun(id, runId);
  if (!run) notFound();

  return (
    <div>
      <div className="mb-4 flex items-center gap-2 text-sm">
        <Link href={`/workspace/${id}`} className="text-blue-400 hover:underline">← Workspace</Link>
      </div>
      <div className="mb-2 flex items-center justify-between gap-4">
        <h2 className="text-xl font-semibold">Run: {run.id}</h2>
        <Link
          className="text-sm text-blue-400 hover:underline"
          href={`/workspace/${id}/run/${run.id}/review`}
        >
          Open review
        </Link>
      </div>
      <p className="text-sm text-neutral-400 mb-6">
        {new Date(run.created_at).toLocaleString()} · {run.status} · {run.project_name}
      </p>

      <DecisionSummary run={run} />
      <CaveatBanner run={run} />

      <ComparisonTable
        tasks={run.tasks}
        configurations={run.configurations}
        results={run.results}
        decision={run.decision}
      />
      <CellDetail run={run} artifactBasePath={`/workspace/${id}/run/${runId}/artifact`} />
      <AnnotationPanel runId={run.id} cells={run.results} />
    </div>
  );
}
