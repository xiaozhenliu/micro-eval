import fs from "node:fs";
import { NextResponse } from "next/server";
import { isServerMode } from "@/lib/server-mode";
import { getWorkspaceRunsDir, resolveWorkspaceRunDir, resolveInsideRunDir } from "@/lib/workspace-api";
import { RunSchema } from "@/lib/schema";

interface RouteContext {
  params: Promise<{ id: string; runId: string }>;
}

const RUN_ID_RE = /^(?!\.+$)[A-Za-z0-9_.:-]+$/;

export async function GET(request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const { id, runId } = await context.params;
  if (!RUN_ID_RE.test(runId)) {
    return NextResponse.json({ error: "invalid run id" }, { status: 400 });
  }

  const runsDir = getWorkspaceRunsDir(id);
  if (!runsDir) return NextResponse.json({ error: "workspace not found" }, { status: 404 });

  const runDir = resolveWorkspaceRunDir(id, runId);
  if (!runDir) return NextResponse.json({ error: "run not found" }, { status: 404 });

  const runJsonPath = resolveInsideRunDir(runDir, "run.json");
  if (!runJsonPath || !fs.existsSync(runJsonPath)) {
    return NextResponse.json({ error: "run not found" }, { status: 404 });
  }

  let run;
  try {
    run = RunSchema.parse(JSON.parse(fs.readFileSync(runJsonPath, "utf-8")));
  } catch (err) {
    return NextResponse.json({ error: "failed to parse run", detail: String(err) }, { status: 500 });
  }

  const artifactId = new URL(request.url).searchParams.get("artifact_id");
  if (!artifactId) {
    // Return list of all artifact refs
    return NextResponse.json(run.artifacts);
  }

  const artifact = run.artifacts.find((a) => a.artifact_id === artifactId);
  if (!artifact) return NextResponse.json({ error: "artifact not found" }, { status: 404 });

  // Every path component between runDir and the artifact file is re-checked
  // for symlinks (round-6 review, 2026-09-12).
  const artifactPath = resolveInsideRunDir(runDir, artifact.path);
  if (!artifactPath || !fs.existsSync(artifactPath)) {
    return NextResponse.json({ error: "artifact not found" }, { status: 404 });
  }

  if (artifact.warning?.includes("skipped_oversized")) {
    return NextResponse.json({ artifact, content: `[${artifact.warning}: ${artifact.path}]` });
  }
  if (artifact.media_type !== "text/plain") {
    return NextResponse.json({
      artifact,
      content: `[${artifact.warning ?? "non-text artifact not displayed"}: ${artifact.path}]`,
    });
  }

  return NextResponse.json({ artifact, content: fs.readFileSync(artifactPath, "utf-8") });
}
