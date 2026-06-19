import path from "node:path";
import fs from "node:fs";
import { NextResponse } from "next/server";
import { isServerMode } from "@/lib/server-mode";
import { getWorkspaceRunsDir } from "@/lib/workspace-api";
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
    const runJsonPath = path.join(runsDir, entry.name, "run.json");
    if (!fs.existsSync(runJsonPath)) continue;
    try {
      const raw = JSON.parse(fs.readFileSync(runJsonPath, "utf-8"));
      const run = RunSchema.parse(raw);

      // Merge decision.json if present
      const decisionPath = path.join(runsDir, entry.name, "decision.json");
      if (fs.existsSync(decisionPath)) {
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
