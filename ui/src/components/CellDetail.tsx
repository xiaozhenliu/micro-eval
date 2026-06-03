import type { Run } from "@/lib/schema";
import Link from "next/link";

export function CellDetail({ run }: { run: Run }) {
  if (run.results.length === 0) return null;
  const artifactsById = new Map(run.artifacts.map((artifact) => [artifact.artifact_id, artifact]));
  const evidenceById = new Map(run.evidence.map((evidence) => [evidence.evidence_id, evidence]));

  return (
    <section className="mt-8">
      <h3 className="text-base font-semibold mb-4">Cell Evidence</h3>
      <div className="space-y-4">
        {run.results.map((result) => (
          <details key={result.cell_id} className="border border-neutral-800 rounded-lg p-4 bg-neutral-950">
            <summary className="cursor-pointer font-mono text-xs">
              {result.task_id} / {result.configuration_id} / rep {result.repetition} — {result.status}
            </summary>
            <div className="mt-4 grid gap-4 md:grid-cols-2 text-sm">
              <div>
                <p className="text-neutral-400 mb-1">Snapshot gate</p>
                <p>{result.snapshot_gate_result?.status ?? "missing"}</p>
                <p className="text-xs text-neutral-500">
                  {(result.snapshot_gate_result?.mismatch_fields ?? []).join(", ") || "no mismatches"}
                </p>
              </div>
              <div>
                <p className="text-neutral-400 mb-1">Workspace</p>
                <p className="font-mono text-xs break-all">{result.cell_snapshot?.workspace_path ?? "missing"}</p>
                <p className="text-xs text-neutral-500">cleanup: {result.cell_snapshot?.cleanup_status ?? "n/a"}</p>
              </div>
            </div>
            <div className="mt-4">
              <p className="text-neutral-400 mb-2">Evidence</p>
              <ul className="space-y-2 text-sm">
                {result.evidence_refs.map((evidenceId) => {
                  const evidence = evidenceById.get(evidenceId);
                  return (
                    <li key={evidenceId} className="border-l border-neutral-700 pl-3">
                      <p>{evidence?.summary ?? evidenceId}</p>
                      <p className="text-xs text-neutral-500">{evidence?.kind} · {evidence?.severity}</p>
                    </li>
                  );
                })}
              </ul>
            </div>
            <div className="mt-4">
              <p className="text-neutral-400 mb-2">Artifacts</p>
              <ul className="space-y-1 text-xs font-mono">
                {result.artifact_refs.map((artifactId) => {
                  const artifact = artifactsById.get(artifactId);
                  return (
                    <li key={artifactId}>
                      {artifact ? (
                        <Link
                          className="text-blue-400 hover:underline"
                          href={`/run/${run.id}/artifact/${encodeURIComponent(artifact.artifact_id)}`}
                        >
                          {artifact.kind}: {artifact.path}
                        </Link>
                      ) : (
                        artifactId
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}
