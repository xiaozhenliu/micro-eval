import type { Run } from "@/lib/schema";

export function DecisionSummary({ run }: { run: Run }) {
  const decision = run.decision;
  return (
    <section className="bg-neutral-900 border border-neutral-800 rounded-lg p-4 mb-6">
      <div className="flex flex-wrap gap-4 items-center justify-between">
        <div>
          <p className="text-xs text-neutral-400 mb-1">Decision</p>
          <h3 className="text-lg font-semibold">{decision?.verdict ?? "inconclusive"}</h3>
        </div>
        <div>
          <p className="text-xs text-neutral-400 mb-1">Confidence</p>
          <p>{decision?.confidence ?? "low"}</p>
        </div>
        <div>
          <p className="text-xs text-neutral-400 mb-1">Evidence refs</p>
          <p>{decision?.evidence_refs.length ?? 0}</p>
        </div>
        <div>
          <p className="text-xs text-neutral-400 mb-1">Replay digest</p>
          <p className="font-mono text-xs">{run.replay_canonical?.digest.slice(0, 12) ?? "missing"}</p>
        </div>
      </div>
      {decision?.recommended_action && (
        <p className="mt-3 text-sm text-neutral-300">{decision.recommended_action}</p>
      )}
    </section>
  );
}
