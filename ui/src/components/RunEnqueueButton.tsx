"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { PlanSummarySchema, type PlanSummary } from "@/lib/project-schema";
import { getMemberName, setMemberName as persistMemberName } from "@/lib/member-identity";
import { INVALID_GIT_REF_REASON } from "@/lib/refusal-hints";

interface RunEnqueueButtonProps {
  workspaceId: string;
  memberName?: string;
  /** When set, the button is disabled and this reason is shown underneath (e.g. missing configurations/tasks). */
  disabledReason?: string;
}

/** Append the route's fixed hint for the known invalid-ref reason, if any. */
function refusalText(
  body: { error?: string; detail?: string; reason?: unknown; hint?: unknown },
  fallback: string,
): string {
  const base = body.detail || body.error || fallback;
  if (body.reason === INVALID_GIT_REF_REASON && typeof body.hint === "string" && body.hint.length > 0) {
    return `${base}\n${body.hint}`;
  }
  return base;
}

export function RunEnqueueButton({ workspaceId, memberName: memberNameProp, disabledReason }: RunEnqueueButtonProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [memberName, setMemberNameState] = useState(() => memberNameProp ?? getMemberName());
  const [showNameInput, setShowNameInput] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [planSummary, setPlanSummary] = useState<PlanSummary | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);

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
        // Carry the plan digest the user saw in the preview so the server
        // can refuse a stale enqueue if tasks or configuration changed in
        // the meantime (round-6/7 reviews, 2026-09-12/13).
        body: JSON.stringify({ expected_plan_digest: planSummary?.plan_digest ?? null }),
      });

      if (res.status === 409) {
        const body = await res.json().catch(() => ({}) as { error?: string; detail?: string });
        setError(refusalText(body, "configuration changed since the preview; review the new preview"));
        // The preview is now stale — drop it so the next click fetches a
        // fresh one instead of retrying with the same expected_plan_digest.
        setPlanSummary(null);
        setShowConfirm(false);
        setLoading(false);
        return;
      }

      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string; detail?: string; reason?: unknown; hint?: unknown };
        throw new Error(refusalText(body, `HTTP ${res.status}`));
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
        const parsed = PlanSummarySchema.safeParse(await res.json());
        setPlanSummary(parsed.success ? parsed.data : null);
      } else if (res.status === 409 || res.status === 404 || res.status === 502) {
        // A plan-build refusal includes a detail on 502; keep a transient
        // summary failure without detail on the existing fallback path.
        const body = (await res.json().catch(() => ({}))) as { error?: string; detail?: string; reason?: unknown; hint?: unknown };
        if (res.status !== 502 || body.detail) {
          setError(refusalText(body, `HTTP ${res.status}`));
          setPlanSummary(null);
          return;
        }
        setPlanSummary(null);
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
        disabled={loading || showConfirm || Boolean(disabledReason)}
        className="inline-flex items-center gap-2 px-4 py-2 rounded bg-blue-600 text-white text-sm font-medium hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {loading && (
          <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
        )}
        {loading ? "Loading…" : "Enqueue Run"}
      </button>
      {disabledReason && (
        <p className="text-xs text-amber-400">{disabledReason}</p>
      )}
      {error && (
        <p className="text-xs text-red-400 whitespace-pre-line">{error}</p>
      )}
      {showConfirm && (
        <div className="rounded border border-neutral-700 bg-neutral-900 p-4 space-y-3">
          {planSummary ? (
            <>
              <p className="text-sm font-medium">Run Preview</p>
              <p className="text-sm text-neutral-300">
                {planSummary.repetitions_uniform ? (
                  <>{planSummary.tasks} task{planSummary.tasks !== 1 ? "s" : ""} × {planSummary.configurations} config{planSummary.configurations !== 1 ? "s" : ""} × {planSummary.repetitions} rep{planSummary.repetitions !== 1 ? "s" : ""} = {planSummary.total_cells} cell{planSummary.total_cells !== 1 ? "s" : ""}</>
                ) : (
                  <>{planSummary.tasks} task{planSummary.tasks !== 1 ? "s" : ""} × {planSummary.configurations} config{planSummary.configurations !== 1 ? "s" : ""} = {planSummary.total_cells} cell{planSummary.total_cells !== 1 ? "s" : ""} (repetitions vary per configuration)</>
                )}
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
