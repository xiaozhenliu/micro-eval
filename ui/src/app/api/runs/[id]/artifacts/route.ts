import { NextResponse } from "next/server";
import { getArtifact } from "@/lib/api";

interface RouteContext {
  params: Promise<{ id: string }>;
}

export async function GET(request: Request, context: RouteContext) {
  const { id } = await context.params;
  const artifactId = new URL(request.url).searchParams.get("artifact_id");
  if (!artifactId) return NextResponse.json({ error: "artifact_id is required" }, { status: 400 });
  const artifact = await getArtifact(id, artifactId);
  if (!artifact) return NextResponse.json({ error: "artifact not found" }, { status: 404 });
  return NextResponse.json(artifact);
}
