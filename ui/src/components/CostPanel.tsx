import type { DecisionReport } from "@/lib/schema";

export function CostPanel({ decision }: { decision: DecisionReport | null }) {
  const rows = Object.entries(decision?.aggregation.per_configuration ?? {});
  return (
    <section className="border border-neutral-800 rounded-lg bg-neutral-950 p-4">
      <h3 className="text-base font-semibold mb-3">Cost and latency</h3>
      {rows.length === 0 ? (
        <p className="text-sm text-neutral-500">No aggregation data.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-neutral-800 text-left text-neutral-400">
                <th className="pb-2 pr-4 font-medium">Configuration</th>
                <th className="pb-2 pr-4 font-medium">Cost</th>
                <th className="pb-2 pr-4 font-medium">Source</th>
                <th className="pb-2 pr-4 font-medium">Mean latency</th>
                <th className="pb-2 pr-4 font-medium">Median latency</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([configuration, stats]) => (
                <tr key={configuration} className="border-b border-neutral-800/50">
                  <td className="py-2 pr-4 font-mono text-xs">{configuration}</td>
                  <td className="py-2 pr-4">{formatCost(stats.total_cost?.amount ?? null)}</td>
                  <td className="py-2 pr-4 text-neutral-400">{stats.total_cost?.source ?? "unavailable"}</td>
                  <td className="py-2 pr-4">{formatMs(stats.mean_latency_ms)}</td>
                  <td className="py-2 pr-4">{formatMs(stats.median_latency_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function formatCost(value: number | null): string {
  return value == null ? "Cost data unavailable" : `$${value.toFixed(4)}`;
}

function formatMs(value: number | null): string {
  return value == null ? "--" : `${(value / 1000).toFixed(2)}s`;
}
