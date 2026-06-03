import type { CellResult } from "@/lib/schema";

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
}

export function ComparisonTable({ tasks, configurations, results }: ComparisonTableProps) {
  const getResults = (taskId: string, configurationId: string) =>
    results.filter((r) => r.task_id === taskId && r.configuration_id === configurationId);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-neutral-800 text-neutral-400 text-left">
            <th className="pb-3 pr-4 font-medium">Task</th>
            {configurations.map((configuration) => (
              <th key={configuration} className="pb-3 pr-4 font-medium">{configuration}</th>
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
