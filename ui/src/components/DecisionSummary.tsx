import type { Run } from "@/lib/schema";

export function DecisionSummary({ run }: { run: Run }) {
  const decision = run.decision;
  const stats = decision?.aggregation.per_configuration ?? {};
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
          <p className="text-xs text-neutral-400 mb-1">Decision report</p>
          <p className="font-mono text-xs">{decision?.decision_report_id ? decision.decision_report_id.split("::").slice(-1)[0] : "embedded"}</p>
        </div>
        <div>
          <p className="text-xs text-neutral-400 mb-1">Replay digest</p>
          <p className="font-mono text-xs">{run.replay_canonical?.digest.slice(0, 12) ?? "missing"}</p>
        </div>
      </div>
      {Object.keys(stats).length > 0 && (
        <div className="mt-4 grid gap-2 md:grid-cols-2">
          {Object.entries(stats).map(([configuration, row]) => (
            <div key={configuration} className="rounded border border-neutral-800 p-3 text-sm">
              <div className="font-mono text-xs text-neutral-300">{configuration}</div>
              <div className="mt-1 text-neutral-400">
                pass {formatRate(row.pass_rate)} · n={row.n_cells} · latency {formatMs(row.mean_latency_ms)}
                {row.caveats.includes("low_sample") && <span className="text-amber-300"> · low sample</span>}
              </div>
              {!hasOnlyPassAt1(row.pass_at_k) && (
                <div className="mt-1 text-xs text-neutral-500">pass@k {formatPassAtK(row.pass_at_k)}</div>
              )}
            </div>
          ))}
        </div>
      )}
      {decision?.recommended_action && (
        <p className="mt-3 text-sm text-neutral-300">{decision.recommended_action}</p>
      )}
    </section>
  );
}

function formatRate(value: number | null): string {
  return value == null ? "--" : `${Math.round(value * 100)}%`;
}

function formatMs(value: number | null): string {
  return value == null ? "--" : `${(value / 1000).toFixed(2)}s`;
}

function formatPassAtK(value: Record<string, number> | null): string {
  if (!value) return "--";
  return Object.entries(value)
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([k, v]) => `@${k} ${Math.round(v * 100)}%`)
    .join(", ");
}

function hasOnlyPassAt1(value: Record<string, number> | null): boolean {
  if (!value) return false;
  const keys = Object.keys(value);
  return keys.length === 1 && keys[0] === "1";
}
