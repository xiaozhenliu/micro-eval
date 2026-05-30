import type { RunResult } from "@/lib/schema";

const statusColors: Record<RunResult["status"], string> = {
  pass: "text-green-400",
  fail: "text-red-400",
  error: "text-amber-400",
  timeout: "text-amber-400",
};

interface ComparisonTableProps {
  tasks: string[];
  results: RunResult[];
  baselineAgent: string;
  candidateAgent: string;
}

export function ComparisonTable({
  tasks,
  results,
  baselineAgent,
  candidateAgent,
}: ComparisonTableProps) {
  const getResult = (taskId: string, agent: string) =>
    results.find((r) => r.task_id === taskId && r.agent_name === agent);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-neutral-800 text-neutral-400 text-left">
            <th className="pb-3 pr-4 font-medium">Task</th>
            <th className="pb-3 pr-4 font-medium">{baselineAgent}</th>
            <th className="pb-3 pr-4 font-medium">{candidateAgent}</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((taskId) => {
            const baseline = getResult(taskId, baselineAgent);
            const candidate = getResult(taskId, candidateAgent);
            return (
              <tr key={taskId} className="border-b border-neutral-800/50">
                <td className="py-3 pr-4 font-mono text-xs">{taskId}</td>
                <td className="py-3 pr-4">
                  {baseline ? (
                    <span className={statusColors[baseline.status]}>
                      {baseline.status}
                      {baseline.score != null && ` (${baseline.score.toFixed(1)})`}
                    </span>
                  ) : (
                    <span className="text-neutral-500">--</span>
                  )}
                </td>
                <td className="py-3 pr-4">
                  {candidate ? (
                    <span className={statusColors[candidate.status]}>
                      {candidate.status}
                      {candidate.score != null && ` (${candidate.score.toFixed(1)})`}
                    </span>
                  ) : (
                    <span className="text-neutral-500">--</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
