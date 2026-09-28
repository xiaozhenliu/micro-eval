import path from "node:path";
import fs from "node:fs";
import { NextResponse } from "next/server";
import { isServerMode } from "@/lib/server-mode";
import { getWorkspaceRunsDir } from "@/lib/workspace-api";
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

  const runDir = path.join(runsDir, runId);
  const runJsonPath = path.join(runDir, "run.json");
  if (!fs.existsSync(runJsonPath)) {
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

  // Path traversal check
  const artifactPath = path.resolve(runDir, artifact.path);
  const realRunDir = fs.realpathSync(runDir);
  if (!artifactPath.startsWith(realRunDir + path.sep)) {
    return NextResponse.json({ error: "artifact not found" }, { status: 404 });
  }
  if (!fs.existsSync(artifactPath)) {
    return NextResponse.json({ error: "artifact not found" }, { status: 404 });
  }
  const realArtifactPath = fs.realpathSync(artifactPath);
  if (!realArtifactPath.startsWith(realRunDir + path.sep)) {
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

  return NextResponse.json({ artifact, content: fs.readFileSync(realArtifactPath, "utf-8") });
}
