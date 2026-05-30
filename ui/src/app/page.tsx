import { listRuns } from "@/lib/api";
import { RunList } from "@/components/RunList";

export default async function HomePage() {
  const runs = await listRuns();

  return (
    <div>
      <h2 className="text-xl font-semibold mb-6">Runs</h2>
      <RunList runs={runs} />
    </div>
  );
}
