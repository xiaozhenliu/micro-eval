"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

interface RunEnqueueButtonProps {
  workspaceId: string;
  memberName: string;
}

export function RunEnqueueButton({ workspaceId, memberName }: RunEnqueueButtonProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`/api/workspaces/${workspaceId}/runs/enqueue`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Micro-Eval-Member": memberName,
        },
      });

      if (!res.ok) {
        const body = await res.text();
        throw new Error(body || `HTTP ${res.status}`);
      }

      const data = await res.json();
      if (data.job_id) {
        router.push(`/workspace/${workspaceId}/jobs/${data.job_id}`);
      } else {
        router.refresh();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to enqueue run");
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <button
        onClick={handleClick}
        disabled={loading}
        className="inline-flex items-center gap-2 px-4 py-2 rounded bg-blue-600 text-white text-sm font-medium hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {loading && (
          <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
        )}
        {loading ? "Enqueueing…" : "Enqueue Run"}
      </button>
      {error && (
        <p className="text-xs text-red-400">{error}</p>
      )}
    </div>
  );
}
