import { QueueJobCard, type QueueJob } from "@/components/QueueJobCard";

export interface QueueDashboardData {
  running: QueueJob | null;
  queued: QueueJob[];
  recent_completed: QueueJob[];
}

export function QueueDashboard({ data }: { data: QueueDashboardData }) {
  return (
    <div className="space-y-8">
      <section>
        <h3 className="text-base font-semibold mb-3">Running</h3>
        {data.running ? (
          <QueueJobCard job={data.running} />
        ) : (
          <p className="text-sm text-neutral-500">No job currently running.</p>
        )}
      </section>

      <section>
        <h3 className="text-base font-semibold mb-3">
          Queued
          {data.queued.length > 0 && (
            <span className="ml-2 text-xs font-normal text-neutral-400">
              ({data.queued.length})
            </span>
          )}
        </h3>
        {data.queued.length > 0 ? (
          <div className="space-y-3">
            {data.queued.map((job) => (
              <QueueJobCard key={job.job_id} job={job} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-neutral-500">Queue is empty.</p>
        )}
      </section>

      <section>
        <h3 className="text-base font-semibold mb-3">
          Recently Completed
          {data.recent_completed.length > 0 && (
            <span className="ml-2 text-xs font-normal text-neutral-400">
              ({data.recent_completed.length})
            </span>
          )}
        </h3>
        {data.recent_completed.length > 0 ? (
          <div className="space-y-3">
            {data.recent_completed.map((job) => (
              <QueueJobCard key={job.job_id} job={job} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-neutral-500">No completed jobs yet.</p>
        )}
      </section>
    </div>
  );
}
