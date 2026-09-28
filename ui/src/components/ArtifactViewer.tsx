import type { ArtifactRef } from "@/lib/schema";

export function ArtifactViewer({ artifact, content }: { artifact: ArtifactRef; content: string }) {
  return (
    <section className="border border-neutral-800 rounded-lg p-4 bg-neutral-950">
      <h3 className="font-semibold mb-2">{artifact.kind}: {artifact.path}</h3>
      {artifact.warning && <p className="text-amber-300 text-sm mb-2">{artifact.warning}</p>}
      <pre className="overflow-auto text-xs whitespace-pre-wrap text-neutral-200">{content}</pre>
    </section>
  );
}
