import fs from "node:fs";
import { NextResponse } from "next/server";
import { isServerMode } from "@/lib/server-mode";
import { getWorkspaceRunsDir, resolveWorkspaceRunDir, resolveInsideRunDir } from "@/lib/workspace-api";
import { RunSchema } from "@/lib/schema";

interface RouteContext {
  params: Promise<{ id: string }>;
}

export async function GET(_request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const { id } = await context.params;
  const runsDir = getWorkspaceRunsDir(id);
  if (!runsDir) return NextResponse.json({ error: "workspace not found" }, { status: 404 });

  if (!fs.existsSync(runsDir)) return NextResponse.json([]);

  const entries = fs.readdirSync(runsDir, { withFileTypes: true });
  const runs = [];

  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    // Same symlink-free resolution as the per-run routes: a run.json or
    // decision.json swapped for a symlink is skipped, not followed.
    const runDir = resolveWorkspaceRunDir(id, entry.name);
    if (!runDir) continue;
    const runJsonPath = resolveInsideRunDir(runDir, "run.json");
    if (!runJsonPath || !fs.existsSync(runJsonPath)) continue;
    try {
      const raw = JSON.parse(fs.readFileSync(runJsonPath, "utf-8"));
      const run = RunSchema.parse(raw);

      // Merge decision.json if present
      const decisionPath = resolveInsideRunDir(runDir, "decision.json");
      if (decisionPath && fs.existsSync(decisionPath)) {
        const decision = JSON.parse(fs.readFileSync(decisionPath, "utf-8"));
        runs.push({ ...run, decision });
      } else {
        runs.push(run);
      }
    } catch {
      continue;
    }
  }

  runs.sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
  return NextResponse.json(runs);
}
