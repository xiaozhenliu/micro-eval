import Link from "next/link";
import { isServerMode, getServerDataRoot } from "@/lib/server-mode";
import { notFound } from "next/navigation";
import { QueueDashboard } from "@/components/QueueDashboard";
import type { QueueDashboardData } from "@/components/QueueDashboard";
import { queryQueue } from "@/lib/server-validation";

function fetchQueueData(): QueueDashboardData {
  try {
    const dashboard = queryQueue(
      `result = db.get_queue_dashboard()\nprint(json.dumps(result))`,
    ) as QueueDashboardData;
    return dashboard;
  } catch {
    // queue.db may not exist yet (no jobs ever enqueued)
    return { running: null, queued: [], recent_completed: [] };
  }
}

export default function QueuePage() {
  if (!isServerMode()) notFound();

  const data = fetchQueueData();

  const totalActive = (data.running ? 1 : 0) + data.queued.length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Link href="/" className="text-sm text-blue-400 hover:underline">← Home</Link>
          </div>
          <h2 className="text-xl font-semibold">Run Queue</h2>
          <p className="mt-1 text-sm text-neutral-400">
            {totalActive > 0 ? `${totalActive} active job${totalActive !== 1 ? "s" : ""}` : "No active jobs"}
          </p>
        </div>
      </div>

      <QueueDashboard data={data} />
    </div>
  );
}
