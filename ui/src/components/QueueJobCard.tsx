import MemberBadge from "@/components/MemberBadge";

export interface QueueJob {
  job_id: string;
  workspace_id: string;
  owner: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  enqueued_at: string;
  started_at: string | null;
  progress: number | null;
  cancel_requested_at: string | null;
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

function statusStyle(status: QueueJob["status"]): { text: string; className: string } {
  switch (status) {
    case "running":
      return { text: "running", className: "text-blue-400" };
    case "queued":
      return { text: "queued", className: "text-amber-400" };
    case "completed":
      return { text: "completed", className: "text-green-400" };
    case "failed":
      return { text: "failed", className: "text-red-400" };
    case "cancelled":
      return { text: "cancelled", className: "text-neutral-500" };
    default:
      return { text: status, className: "text-neutral-400" };
  }
}

export function QueueJobCard({ job }: { job: QueueJob }) {
  const { text: statusText, className: statusClass } = statusStyle(job.status);
  const isCancelPending = job.cancel_requested_at != null && job.status === "running";

  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-lg p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p className="font-mono text-xs text-neutral-400 truncate">
            Job: {job.job_id}
          </p>
          <p className="mt-1 text-sm text-neutral-200 truncate">
            Workspace: {job.workspace_id}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <span className={`text-xs font-medium ${statusClass}`}>{statusText}</span>
          {isCancelPending && (
            <span className="text-xs text-amber-400">cancel requested</span>
          )}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-neutral-400">
        <span>
          Owner: <MemberBadge name={job.owner} />
        </span>
        <span>Enqueued: {formatTimestamp(job.enqueued_at)}</span>
        {job.started_at && (
          <span>Started: {formatTimestamp(job.started_at)}</span>
        )}
      </div>

      {job.status === "running" && job.progress != null && (
        <div className="mt-3">
          <div className="flex items-center justify-between text-xs text-neutral-400 mb-1">
            <span>Progress</span>
            <span>{Math.round(job.progress * 100)}%</span>
          </div>
          <div className="h-1.5 bg-neutral-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 rounded-full transition-all"
              style={{ width: `${Math.round(job.progress * 100)}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
