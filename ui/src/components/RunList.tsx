import Link from "next/link";
import type { Run } from "@/lib/schema";

function calculatePassRate(results: Run["results"], agentName: string): string {
  const agentResults = results.filter((r) => r.agent_name === agentName);
  if (agentResults.length === 0) return "N/A";
  const passed = agentResults.filter((r) => r.status === "pass").length;
  return `${Math.round((passed / agentResults.length) * 100)}%`;
}

function formatTimestamp(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function RunList({ runs }: { runs: Run[] }) {
  if (runs.length === 0) {
    return (
      <div className="text-center py-16 text-neutral-400">
        <p className="text-lg">No runs yet.</p>
        <p className="mt-2 text-sm">
          Run <code className="bg-neutral-800 px-2 py-0.5 rounded">micro-eval run</code> to get started.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-neutral-800 text-neutral-400 text-left">
            <th className="pb-3 pr-4 font-medium">Timestamp</th>
            <th className="pb-3 pr-4 font-medium">Baseline</th>
            <th className="pb-3 pr-4 font-medium">Candidate</th>
            <th className="pb-3 pr-4 font-medium">Pass Rate</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id} className="border-b border-neutral-800/50 hover:bg-neutral-900/50">
              <td className="py-3 pr-4">
                <Link href={`/run/${run.id}`} className="text-blue-400 hover:underline">
                  {formatTimestamp(run.timestamp)}
                </Link>
              </td>
              <td className="py-3 pr-4 font-mono text-xs">{run.baseline_agent}</td>
              <td className="py-3 pr-4 font-mono text-xs">{run.candidate_agent}</td>
              <td className="py-3 pr-4">
                {calculatePassRate(run.results, run.baseline_agent)} / {calculatePassRate(run.results, run.candidate_agent)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
