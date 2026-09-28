import path from "node:path";
import fs from "node:fs";
import { NextResponse } from "next/server";
import { isServerMode } from "@/lib/server-mode";
import { getWorkspaceRunsDir } from "@/lib/workspace-api";
import { RunSchema, DecisionReportSchema } from "@/lib/schema";

interface RouteContext {
  params: Promise<{ id: string; runId: string }>;
}

const RUN_ID_RE = /^(?!\.+$)[A-Za-z0-9_.:-]+$/;

export async function GET(_request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const { id, runId } = await context.params;
  if (!RUN_ID_RE.test(runId)) {
    return NextResponse.json({ error: "invalid run id" }, { status: 400 });
  }

  const runsDir = getWorkspaceRunsDir(id);
  if (!runsDir) return NextResponse.json({ error: "workspace not found" }, { status: 404 });

  const runDir = path.join(runsDir, runId);
  const runJsonPath = path.join(runDir, "run.json");
  if (!fs.existsSync(runJsonPath)) {
    return NextResponse.json({ error: "run not found" }, { status: 404 });
  }

  try {
    const raw = JSON.parse(fs.readFileSync(runJsonPath, "utf-8"));
    const run = RunSchema.parse(raw);

    const decisionPath = path.join(runDir, "decision.json");
    if (fs.existsSync(decisionPath)) {
      const decision = DecisionReportSchema.parse(
        JSON.parse(fs.readFileSync(decisionPath, "utf-8")),
      );
      return NextResponse.json({ ...run, decision });
    }
    return NextResponse.json(run);
  } catch (err) {
    return NextResponse.json(
      { error: "failed to parse run", detail: String(err) },
      { status: 500 },
    );
  }
}
