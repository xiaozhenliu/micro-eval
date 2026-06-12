import Link from "next/link";
import type { CellResult } from "@/lib/schema";

interface MatrixHeatmapProps {
  runId: string;
  tasks: string[];
  configurations: string[];
  results: CellResult[];
}

export function MatrixHeatmap({ runId, tasks, configurations, results }: MatrixHeatmapProps) {
  const cells = (taskId: string, configurationId: string) =>
    results.filter((result) => result.task_id === taskId && result.configuration_id === configurationId);

  return (
    <section className="border border-neutral-800 rounded-lg bg-neutral-950 p-4">
      <h3 className="text-base font-semibold mb-3">Task × configuration heatmap</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-neutral-800 text-left text-neutral-400">
              <th className="pb-2 pr-4 font-medium">Task</th>
              {configurations.map((configuration) => (
                <th key={configuration} className="pb-2 pr-4 font-medium">{configuration}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tasks.map((taskId) => (
              <tr key={taskId} className="border-b border-neutral-800/50">
                <td className="py-2 pr-4 font-mono text-xs">{taskId}</td>
                {configurations.map((configuration) => {
                  const group = cells(taskId, configuration);
                  const first = group[0];
                  const passRate = group.length
                    ? group.filter((cell) => (cell.pass_fail == null ? cell.status === "pass" : cell.pass_fail === "pass")).length / group.length
                    : null;
                  return (
                    <td key={configuration} className="py-2 pr-4">
                      {first ? (
                        <Link
                          className={`inline-block min-w-24 rounded px-2 py-1 text-center text-xs ${color(passRate, first.status)}`}
                          href={`/run/${runId}/review#${encodeURIComponent(first.cell_id)}`}
                        >
                          {formatRate(passRate)} · {group.length} rep
                          {first.failure_mode && <span className="block text-[10px] opacity-80">{first.failure_mode}</span>}
                        </Link>
                      ) : (
                        <span className="text-neutral-600">missing</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function formatRate(value: number | null): string {
  return value == null ? "--" : `${Math.round(value * 100)}%`;
}

function color(passRate: number | null, status: CellResult["status"]): string {
  if (status === "error" || status === "timeout") return "bg-amber-900/50 text-amber-200";
  if (passRate == null) return "bg-neutral-800 text-neutral-300";
  if (passRate >= 0.8) return "bg-green-900/50 text-green-200";
  if (passRate > 0) return "bg-yellow-900/50 text-yellow-200";
  return "bg-red-900/50 text-red-200";
}
