import type { Run } from "@/lib/schema";
import Link from "next/link";
import { TraceViewer } from "@/components/TraceViewer";

// Minimal shape needed to derive a plain-language explanation for a failed cell.
// Kept structurally compatible with CellResult so it can be reused/tested standalone.
type ExplainableResult = {
  status: string;
  exit_code?: number | null;
};

// Maps a cell's raw status/exit_code into a one-line human-readable explanation.
// Returns null when the cell passed cleanly and no explanation is needed.
export function cellExplanation(result: ExplainableResult): string | null {
  const { status, exit_code: exitCode } = result;

  if (status === "timeout") {
    return "The agent hit the per-cell timeout.";
  }
  if (status === "error" || (exitCode != null && exitCode !== 0)) {
    return `The agent process exited with an error (exit code ${exitCode ?? "unknown"}).`;
  }
  // Process ran to completion but validation/scoring rejected the output.
  if (status === "fail") {
    return "Process exited normally, but the output failed validation (expected text missing).";
  }
  // status === "pass" (or unrecognized) — nothing to explain.
  return null;
}

export function CellDetail({ run, artifactBasePath }: { run: Run; artifactBasePath?: string }) {
  if (run.results.length === 0) return null;
  const basePath = artifactBasePath ?? `/run/${run.id}/artifact`;
  const artifactsById = new Map(run.artifacts.map((artifact) => [artifact.artifact_id, artifact]));
  const evidenceById = new Map(run.evidence.map((evidence) => [evidence.evidence_id, evidence]));
  const tracesByRef = new Map(run.traces.map((trace) => [`${trace.provider}:${trace.trace_id}`, trace]));

  return (
    <section className="mt-8">
      <h3 className="text-base font-semibold mb-4">Cell Evidence</h3>
      <div className="space-y-4">
        {run.results.map((result) => (
          <details id={result.cell_id} key={result.cell_id} className="border border-neutral-800 rounded-lg p-4 bg-neutral-950">
            <summary className="cursor-pointer font-mono text-xs">
              {result.task_id} / {result.configuration_id} / rep {result.repetition} — {result.status}
            </summary>
            {cellExplanation(result) ? (
              <p className="mt-3 px-3 py-2 rounded bg-amber-950/30 border border-amber-900/40 text-sm text-amber-200">
                {cellExplanation(result)}
              </p>
            ) : null}
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
              <TraceViewer traces={result.trace_refs.map((traceRef) => tracesByRef.get(traceRef)).filter((trace) => trace != null)} />
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
                          href={`${basePath}/${encodeURIComponent(artifact.artifact_id)}`}
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
