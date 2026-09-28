import Link from "next/link";
import type { Run } from "@/lib/schema";

function formatTimestamp(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function passRate(run: Run, configurationId: string): string {
  const stats = run.decision?.aggregation.per_configuration[configurationId];
  if (stats) return stats.pass_rate == null ? "N/A" : `${Math.round(stats.pass_rate * 100)}%`;
  const results = run.results.filter((r) => r.configuration_id === configurationId);
  if (results.length === 0) return "N/A";
  const passed = results.filter((r) =>
    r.pass_fail == null ? r.status === "pass" : r.pass_fail === "pass"
  ).length;
  return `${Math.round((passed / results.length) * 100)}%`;
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
            <th className="pb-3 pr-4 font-medium">Created</th>
            <th className="pb-3 pr-4 font-medium">Status</th>
            <th className="pb-3 pr-4 font-medium">Decision</th>
            <th className="pb-3 pr-4 font-medium">Configurations</th>
            <th className="pb-3 pr-4 font-medium">Pass Rate</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id} className="border-b border-neutral-800/50 hover:bg-neutral-900/50">
              <td className="py-3 pr-4">
                <Link href={`/run/${run.id}`} className="text-blue-400 hover:underline">
                  {formatTimestamp(run.created_at)}
                </Link>
              </td>
              <td className="py-3 pr-4">{run.status}</td>
              <td className="py-3 pr-4">{run.decision?.verdict ?? "inconclusive"}</td>
              <td className="py-3 pr-4 font-mono text-xs">{run.configurations.join(" / ")}</td>
              <td className="py-3 pr-4">
                {run.configurations.map((id) => `${id}: ${passRate(run, id)}`).join(" · ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
