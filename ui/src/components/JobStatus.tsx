"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getMemberName } from "@/lib/member-identity";
import { JobSchema, type Job } from "@/lib/schema";

export type JobView = Job;

interface JobStatusProps {
  workspaceId: string;
  jobId: string;
  /** Poll interval while the job is queued or running. */
  pollIntervalMs?: number;
  /** Navigate to the run page as soon as the job is done. */
  autoRedirect?: boolean;
}

const TERMINAL_STATUSES = new Set(["done", "failed", "cancelled"]);

function statusClass(status: string): string {
  switch (status) {
    case "running":
      return "text-blue-400";
    case "queued":
      return "text-amber-400";
    case "done":
      return "text-green-400";
    case "failed":
      return "text-red-400";
    case "cancelled":
      return "text-neutral-500";
    default:
      return "text-neutral-400";
  }
}

/**
 * Landing page content after "Enqueue Run" (GRO-556): polls the job until it
 * reaches a terminal state, shows progress and errors, and hands the user
 * over to the run page once a run_id exists.
 */
export function JobStatus({
  workspaceId,
  jobId,
  pollIntervalMs = 2000,
  autoRedirect = true,
}: JobStatusProps) {
  const router = useRouter();
  const [job, setJob] = useState<JobView | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  const load = useCallback(async (): Promise<JobView | null> => {
    try {
      const res = await fetch(
        `/api/workspaces/${encodeURIComponent(workspaceId)}/jobs/${encodeURIComponent(jobId)}`,
        { cache: "no-store" },
      );
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: unknown };
        setLoadError(typeof body.error === "string" ? body.error : `HTTP ${res.status}`);
        return null;
      }
      const parsed = JobSchema.safeParse(await res.json());
      if (!parsed.success) {
        setLoadError("job response has an unexpected shape");
        return null;
      }
      const data = parsed.data;
      setJob(data);
      setLoadError(null);
      return data;
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "failed to load job");
      return null;
    }
  }, [workspaceId, jobId]);

  // Poll until the job reaches a terminal state.
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const tick = async () => {
      const data = await load();
      if (stopped) return;
      if (!data || !TERMINAL_STATUSES.has(data.status)) {
        timer = setTimeout(tick, pollIntervalMs);
      }
    };
    void tick();

    return () => {
      stopped = true;
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [load, pollIntervalMs]);

  // A job fetched by id could belong to a different workspace than the page
  // it's rendered on (e.g. a stale or hand-edited URL). Never send the user
  // to that other workspace's run, and never auto-redirect into it (F13).
  const belongsToOtherWorkspace = job !== null && job.workspace_id !== workspaceId;
  const runHref = job?.run_id && !belongsToOtherWorkspace ? `/workspace/${workspaceId}/run/${job.run_id}` : null;
  const isDone = job?.status === "done";

  useEffect(() => {
    if (autoRedirect && isDone && runHref && !belongsToOtherWorkspace) router.replace(runHref);
  }, [autoRedirect, isDone, runHref, belongsToOtherWorkspace, router]);

  async function handleCancel() {
    const member = getMemberName();
    if (!member) {
      setCancelError("Set your name first (top-right)");
      return;
    }
    setCancelling(true);
    setCancelError(null);
    try {
      const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Micro-Eval-Member": member },
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: unknown };
        throw new Error(typeof body.error === "string" ? body.error : `HTTP ${res.status}`);
      }
      await load();
    } catch (err) {
      setCancelError(err instanceof Error ? err.message : "cancel failed");
    } finally {
      setCancelling(false);
    }
  }

  const progress = job?.progress ?? null;
  const hasCellCounts =
    progress !== null &&
    typeof progress.completed_cells === "number" &&
    typeof progress.total_cells === "number";
  const isActive = job !== null && !TERMINAL_STATUSES.has(job.status);

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4 space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="font-mono text-xs text-neutral-400 truncate">Job: {jobId}</p>
          {job && (
            <p className="mt-1 text-sm">
              Status: <span className={`font-medium ${statusClass(job.status)}`}>{job.status}</span>
              {job.cancel_requested_at && job.status === "running" && (
                <span className="ml-2 text-xs text-amber-400">cancel requested — waiting for active cells</span>
              )}
            </p>
          )}
          {!job && !loadError && <p className="mt-1 text-sm text-neutral-400">Loading…</p>}
        </div>
        {isActive && !job?.cancel_requested_at && (
          <button
            onClick={handleCancel}
            disabled={cancelling}
            className="rounded border border-neutral-700 px-3 py-1.5 text-sm text-neutral-300 hover:border-neutral-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {cancelling ? "Cancelling…" : job?.status === "running" ? "Cancel after active cells" : "Cancel"}
          </button>
        )}
      </div>

      {job?.status === "cancelled" && (
        <p className="text-sm text-neutral-300">
          {hasCellCounts
            ? `Cancelled — retained ${progress.completed_cells}/${progress.total_cells} cells.`
            : "Cancelled before execution."}
        </p>
      )}

      {hasCellCounts && job?.status !== "cancelled" && (
        <p className="text-sm text-neutral-300">
          {progress.completed_cells} / {progress.total_cells} cells
          {progress.current_task && (
            <span className="ml-2 text-xs text-neutral-500">
              current: {progress.current_task}
              {progress.current_config ? ` × ${progress.current_config}` : ""}
            </span>
          )}
        </p>
      )}

      {belongsToOtherWorkspace && (
        <p className="rounded border border-amber-900/60 bg-amber-950/30 px-3 py-2 text-sm text-amber-300">
          This job belongs to a different workspace.
        </p>
      )}

      {loadError && (
        <p className="rounded border border-red-900/60 bg-red-950/30 px-3 py-2 text-sm text-red-300">{loadError}</p>
      )}
      {job?.error && (
        <p className="rounded border border-red-900/60 bg-red-950/30 px-3 py-2 text-sm text-red-300">{job.error}</p>
      )}
      {cancelError && <p className="text-xs text-red-400">{cancelError}</p>}

      <div className="flex flex-wrap items-center gap-4 text-sm">
        {runHref && (
          <Link href={runHref} className="text-blue-400 hover:underline">
            View run
          </Link>
        )}
        <Link href={`/workspace/${workspaceId}`} className="text-neutral-400 hover:text-neutral-200">
          Back to workspace
        </Link>
        <Link href="/queue" className="text-neutral-400 hover:text-neutral-200">
          Queue
        </Link>
      </div>
    </div>
  );
}
