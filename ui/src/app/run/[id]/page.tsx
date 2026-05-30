import { notFound } from "next/navigation";
import { getRun } from "@/lib/api";
import { ComparisonTable } from "@/components/ComparisonTable";
import { AnnotationPanel } from "@/components/AnnotationPanel";

interface PageProps {
  params: Promise<{ id: string }>;
}

function calcStats(results: { status: string; cost_usd: number | null; latency_s: number }[], agent: string, allResults: { agent_name: string; status: string; cost_usd: number | null; latency_s: number }[]) {
  const agentResults = allResults.filter((r) => r.agent_name === agent);
  const total = agentResults.length;
  if (total === 0) return { passRate: 0, cost: 0, latency: 0 };
  const passed = agentResults.filter((r) => r.status === "pass").length;
  const cost = agentResults.reduce((sum, r) => sum + (r.cost_usd || 0), 0);
  const latency = agentResults.reduce((sum, r) => sum + r.latency_s, 0) / total;
  return { passRate: Math.round((passed / total) * 100), cost, latency };
}

export default async function RunPage({ params }: PageProps) {
  const { id } = await params;
  const run = await getRun(id);

  if (!run) {
    notFound();
  }

  const baselineStats = calcStats(run.results, run.baseline_agent, run.results);
  const candidateStats = calcStats(run.results, run.candidate_agent, run.results);

  return (
    <div>
      <h2 className="text-xl font-semibold mb-6">
        Run: {new Date(run.timestamp).toLocaleString()}
      </h2>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <SummaryCard
          label={`${run.baseline_agent} pass`}
          value={`${baselineStats.passRate}%`}
        />
        <SummaryCard
          label={`${run.candidate_agent} pass`}
          value={`${candidateStats.passRate}%`}
        />
        <SummaryCard
          label="Cost diff"
          value={`$${(candidateStats.cost - baselineStats.cost).toFixed(4)}`}
        />
        <SummaryCard
          label="Latency diff"
          value={`${(candidateStats.latency - baselineStats.latency).toFixed(1)}s`}
        />
      </div>

      <ComparisonTable
        tasks={run.tasks}
        results={run.results}
        baselineAgent={run.baseline_agent}
        candidateAgent={run.candidate_agent}
      />

      <AnnotationPanel runId={run.id} tasks={run.tasks} />
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-lg p-4">
      <p className="text-xs text-neutral-400 mb-1">{label}</p>
      <p className="text-lg font-semibold">{value}</p>
    </div>
  );
}
