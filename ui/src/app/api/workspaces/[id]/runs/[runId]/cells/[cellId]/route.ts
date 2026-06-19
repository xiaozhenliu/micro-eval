import path from "node:path";
import fs from "node:fs";
import { NextResponse } from "next/server";
import { isServerMode } from "@/lib/server-mode";
import { getWorkspaceRunsDir } from "@/lib/workspace-api";
import { RunSchema } from "@/lib/schema";

interface RouteContext {
  params: Promise<{ id: string; runId: string; cellId: string }>;
}

const RUN_ID_RE = /^[A-Za-z0-9_.:-]+$/;

export async function GET(_request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const { id, runId, cellId } = await context.params;
  if (!RUN_ID_RE.test(runId)) {
    return NextResponse.json({ error: "invalid run id" }, { status: 400 });
  }

  const runsDir = getWorkspaceRunsDir(id);
  if (!runsDir) return NextResponse.json({ error: "workspace not found" }, { status: 404 });

  const runJsonPath = path.join(runsDir, runId, "run.json");
  if (!fs.existsSync(runJsonPath)) {
    return NextResponse.json({ error: "run not found" }, { status: 404 });
  }

  try {
    const run = RunSchema.parse(JSON.parse(fs.readFileSync(runJsonPath, "utf-8")));
    const decodedCellId = decodeURIComponent(cellId);
    const cell = run.results.find((r) => r.cell_id === decodedCellId);
    if (!cell) return NextResponse.json({ error: "cell not found" }, { status: 404 });
    return NextResponse.json(cell);
  } catch (err) {
    return NextResponse.json(
      { error: "failed to parse run", detail: String(err) },
      { status: 500 },
    );
  }
}
