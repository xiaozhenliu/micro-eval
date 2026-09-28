import { notFound } from "next/navigation";
import fs from "node:fs";
import { resolveWorkspaceRunDir, resolveInsideRunDir } from "@/lib/workspace-api";
import { RunSchema } from "@/lib/schema";
import type { ArtifactRef } from "@/lib/schema";
import { ArtifactViewer } from "@/components/ArtifactViewer";

interface PageProps {
  params: Promise<{ id: string; runId: string; artifactId: string }>;
}

function loadWorkspaceArtifact(
  workspaceId: string,
  runId: string,
  artifactId: string,
): { artifact: ArtifactRef; content: string } | null {
  const runDir = resolveWorkspaceRunDir(workspaceId, runId);
  if (!runDir) return null;

  const runJsonPath = resolveInsideRunDir(runDir, "run.json");
  if (!runJsonPath || !fs.existsSync(runJsonPath)) return null;

  let run;
  try {
    run = RunSchema.parse(JSON.parse(fs.readFileSync(runJsonPath, "utf-8")));
  } catch {
    return null;
  }

  const artifact = run.artifacts.find((item) => item.artifact_id === artifactId);
  if (!artifact) return null;

  // Every path component between runDir and the artifact file is re-checked
  // for symlinks — an artifact whose recorded path was swapped for a symlink
  // after the run completed must not be followed outside the run directory.
  const artifactPath = resolveInsideRunDir(runDir, artifact.path);
  if (!artifactPath || !fs.existsSync(artifactPath)) return null;

  if (artifact.warning?.includes("skipped_oversized")) {
    return { artifact, content: `[${artifact.warning}: ${artifact.path}]` };
  }
  if (artifact.media_type !== "text/plain") {
    return {
      artifact,
      content: `[${artifact.warning ?? "non-text artifact not displayed"}: ${artifact.path}]`,
    };
  }

  return { artifact, content: fs.readFileSync(artifactPath, "utf-8") };
}

export default async function WorkspaceArtifactPage({ params }: PageProps) {
  const { id, runId, artifactId } = await params;
  const result = loadWorkspaceArtifact(id, runId, decodeURIComponent(artifactId));
  if (!result) notFound();
  return <ArtifactViewer artifact={result.artifact} content={result.content} />;
}
