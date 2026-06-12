import type { CellResult, DecisionReport } from "@/lib/schema";

const statusColors: Record<CellResult["status"], string> = {
  pass: "text-green-400",
  fail: "text-red-400",
  error: "text-amber-400",
  timeout: "text-amber-400",
};

interface ComparisonTableProps {
  tasks: string[];
  configurations: string[];
  results: CellResult[];
  decision?: DecisionReport | null;
}

export function ComparisonTable({ tasks, configurations, results, decision }: ComparisonTableProps) {
  const getResults = (taskId: string, configurationId: string) =>
    results.filter((r) => r.task_id === taskId && r.configuration_id === configurationId);
  const stats = decision?.aggregation.per_configuration ?? {};

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-neutral-800 text-neutral-400 text-left">
            <th className="pb-3 pr-4 font-medium">Task</th>
            {configurations.map((configuration) => (
              <th key={configuration} className="pb-3 pr-4 font-medium">
                <div>{configuration}</div>
                {stats[configuration] && (
                  <div className="mt-1 text-xs font-normal text-neutral-500">
                    pass {formatRate(stats[configuration].pass_rate)}
                    {hasOnlyPassAt1(stats[configuration].pass_at_k)
                      ? ""
                      : ` · pass@k ${formatPassAtK(stats[configuration].pass_at_k)}`}
                  </div>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tasks.map((taskId) => (
            <tr key={taskId} className="border-b border-neutral-800/50">
              <td className="py-3 pr-4 font-mono text-xs">{taskId}</td>
              {configurations.map((configuration) => {
                const cells = getResults(taskId, configuration);
                const primary = cells[0];
                return (
                  <td key={configuration} className="py-3 pr-4 align-top">
                    {primary ? (
                      <div>
                        <span className={statusColors[primary.status]}>
                          {primary.status}
                          {primary.score != null && ` (${primary.score.toFixed(1)})`}
                        </span>
                        <div className="mt-1 text-xs text-neutral-500">
                          {cells.length} rep · {primary.latency_s.toFixed(2)}s
                          {primary.snapshot_gate_result?.status !== "pass" && " · caveat"}
                        </div>
                      </div>
                    ) : (
                      <span className="text-neutral-500">--</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatRate(value: number | null): string {
  return value == null ? "--" : `${Math.round(value * 100)}%`;
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
