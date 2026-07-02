"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { getMemberName, setMemberName as persistMemberName } from "@/lib/member-identity";

interface RunEnqueueButtonProps {
  workspaceId: string;
  memberName?: string;
}

export function RunEnqueueButton({ workspaceId, memberName: memberNameProp }: RunEnqueueButtonProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [memberName, setMemberNameState] = useState(memberNameProp ?? "");
  const [showNameInput, setShowNameInput] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [planSummary, setPlanSummary] = useState<{
    tasks: number;
    configurations: number;
    repetitions: number;
    total_cells: number;
    agent_commands: string[];
  } | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);

  // Read the persisted member name on mount (client-only, localStorage).
  useEffect(() => {
    if (memberNameProp) return;
    const stored = getMemberName();
    if (stored) setMemberNameState(stored);
  }, [memberNameProp]);

  async function enqueue(name: string) {
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`/api/workspaces/${workspaceId}/runs/enqueue`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Micro-Eval-Member": name,
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

  async function fetchPlanSummary() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/workspaces/${workspaceId}/plan-summary`);
      if (res.ok) {
        setPlanSummary(await res.json());
      } else {
        // Degrade: allow enqueue without a preview if the summary fetch fails.
        setPlanSummary(null);
      }
      setShowConfirm(true);
    } catch {
      setPlanSummary(null);
      setShowConfirm(true);
    } finally {
      setLoading(false);
    }
  }

  function handleClick() {
    if (!memberName.trim()) {
      setShowNameInput(true);
      setError("Set your name first");
      return;
    }
    fetchPlanSummary();
  }

  function handleSaveName(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault();
    const trimmed = nameDraft.trim();
    if (!trimmed) return;

    persistMemberName(trimmed);
    setMemberNameState(trimmed);
    setShowNameInput(false);
    setError(null);
    fetchPlanSummary();
  }

  function handleConfirm() {
    setShowConfirm(false);
    enqueue(memberName.trim());
  }

  function handleCancel() {
    setShowConfirm(false);
    setPlanSummary(null);
  }

  return (
    <div className="flex flex-col gap-2">
      <button
        onClick={handleClick}
        disabled={loading || showConfirm}
        className="inline-flex items-center gap-2 px-4 py-2 rounded bg-blue-600 text-white text-sm font-medium hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {loading && (
          <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
        )}
        {loading ? "Loading…" : "Enqueue Run"}
      </button>
      {error && (
        <p className="text-xs text-red-400">{error}</p>
      )}
      {showConfirm && (
        <div className="rounded border border-neutral-700 bg-neutral-900 p-4 space-y-3">
          {planSummary ? (
            <>
              <p className="text-sm font-medium">Run Preview</p>
              <p className="text-sm text-neutral-300">
                {planSummary.tasks} task{planSummary.tasks !== 1 ? "s" : ""} × {planSummary.configurations} config{planSummary.configurations !== 1 ? "s" : ""} × {planSummary.repetitions} rep{planSummary.repetitions !== 1 ? "s" : ""} = {planSummary.total_cells} cell{planSummary.total_cells !== 1 ? "s" : ""}
              </p>
              {planSummary.agent_commands.length > 0 && (
                <div className="text-xs text-neutral-400">
                  <p className="mb-1">Agent commands:</p>
                  <ul className="space-y-0.5 font-mono">
                    {planSummary.agent_commands.map((cmd, i) => (
                      <li key={i} className="truncate">{cmd}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-amber-300">Could not load plan preview. You can still enqueue.</p>
          )}
          <div className="flex gap-2">
            <button
              onClick={handleConfirm}
              disabled={loading}
              className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Confirm &amp; Enqueue
            </button>
            <button
              onClick={handleCancel}
              disabled={loading}
              className="rounded border border-neutral-700 px-3 py-1.5 text-sm text-neutral-400 hover:text-neutral-200 disabled:opacity-50 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
      {showNameInput && (
        <form onSubmit={handleSaveName} className="flex items-center gap-2">
          <input
            type="text"
            autoFocus
            value={nameDraft}
            onChange={(e) => setNameDraft(e.target.value)}
            placeholder="Your name"
            className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-sm text-neutral-100"
          />
          <button
            type="submit"
            className="rounded bg-neutral-700 px-2 py-1 text-xs font-medium text-white hover:bg-neutral-600 transition-colors"
          >
            Save &amp; Enqueue
          </button>
        </form>
      )}
    </div>
  );
}
