import { notFound } from "next/navigation";
import { getArtifact } from "@/lib/api";
import { ArtifactViewer } from "@/components/ArtifactViewer";

interface PageProps {
  params: Promise<{ id: string; artifactId: string }>;
}

export default async function ArtifactPage({ params }: PageProps) {
  const { id, artifactId } = await params;
  const artifact = await getArtifact(id, decodeURIComponent(artifactId));
  if (!artifact) notFound();
  return <ArtifactViewer artifact={artifact.artifact} content={artifact.content} />;
}
