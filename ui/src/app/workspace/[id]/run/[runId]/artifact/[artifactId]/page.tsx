import { notFound } from "next/navigation";
import fs from "node:fs";
import path from "node:path";
import { getWorkspaceRunsDir } from "@/lib/workspace-api";
import { RunSchema } from "@/lib/schema";
import type { ArtifactRef } from "@/lib/schema";
import { ArtifactViewer } from "@/components/ArtifactViewer";

interface PageProps {
  params: Promise<{ id: string; runId: string; artifactId: string }>;
}

const RUN_ID_RE = /^[A-Za-z0-9_.:-]+$/;

function loadWorkspaceArtifact(
  workspaceId: string,
  runId: string,
  artifactId: string,
): { artifact: ArtifactRef; content: string } | null {
  if (!RUN_ID_RE.test(runId)) return null;

  const runsDir = getWorkspaceRunsDir(workspaceId);
  if (!runsDir) return null;

  const runDir = path.join(runsDir, runId);
  const runJsonPath = path.join(runDir, "run.json");
  if (!fs.existsSync(runJsonPath)) return null;

  let run;
  try {
    run = RunSchema.parse(JSON.parse(fs.readFileSync(runJsonPath, "utf-8")));
  } catch {
    return null;
  }

  const artifact = run.artifacts.find((item) => item.artifact_id === artifactId);
  if (!artifact) return null;

  // Path traversal check
  const artifactPath = path.resolve(runDir, artifact.path);
  if (!artifactPath.startsWith(path.resolve(runDir) + path.sep)) return null;
  if (!fs.existsSync(artifactPath)) return null;
  const realRunDir = fs.realpathSync(runDir);
  const realArtifactPath = fs.realpathSync(artifactPath);
  if (!realArtifactPath.startsWith(realRunDir + path.sep)) return null;

  if (artifact.warning?.includes("skipped_oversized")) {
    return { artifact, content: `[${artifact.warning}: ${artifact.path}]` };
  }
  if (artifact.media_type !== "text/plain") {
    return {
      artifact,
      content: `[${artifact.warning ?? "non-text artifact not displayed"}: ${artifact.path}]`,
    };
  }

  return { artifact, content: fs.readFileSync(realArtifactPath, "utf-8") };
}

export default async function WorkspaceArtifactPage({ params }: PageProps) {
  const { id, runId, artifactId } = await params;
  const result = loadWorkspaceArtifact(id, runId, decodeURIComponent(artifactId));
  if (!result) notFound();
  return <ArtifactViewer artifact={result.artifact} content={result.content} />;
}
