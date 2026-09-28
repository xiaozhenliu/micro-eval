"use client";

import { useState } from "react";
import { getMemberName } from "@/lib/member-identity";
import type { ConfigurationDraft, ProjectDraft } from "@/lib/project-schema";
import { formatArgvSummary } from "@/lib/agent-presets";
import { ConfigurationForm } from "./ConfigurationForm";

interface ConfigurationListProps {
  workspaceId: string;
  initialDraft: ProjectDraft;
  /** Archived workspaces are read-only: no add/edit/delete controls. */
  readOnly?: boolean;
}

type Mode = { kind: "list" } | { kind: "create" } | { kind: "edit"; configuration: ConfigurationDraft };

export function ConfigurationList({ workspaceId, initialDraft, readOnly = false }: ConfigurationListProps) {
  const [draft, setDraft] = useState(initialDraft);
  const [mode, setMode] = useState<Mode>({ kind: "list" });
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function handleDelete(id: string) {
    const member = getMemberName();
    if (!member) {
      setDeleteError("Set your member name first (top-right)");
      return;
    }
    setDeleting(true);
    setDeleteError(null);
    try {
      const res = await fetch(`/api/workspaces/${workspaceId}/project/configurations/${encodeURIComponent(id)}`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json", "X-Micro-Eval-Member": member },
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || body.error || `HTTP ${res.status}`);
      }
      const updated: ProjectDraft = await res.json();
      setDraft(updated);
      setPendingDeleteId(null);
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Failed to delete configuration");
    } finally {
      setDeleting(false);
    }
  }

  if (mode.kind === "create" || mode.kind === "edit") {
    return (
      <ConfigurationForm
        workspaceId={workspaceId}
        existing={mode.kind === "edit" ? mode.configuration : null}
        onCancel={() => setMode({ kind: "list" })}
        onSaved={(updated) => {
          setDraft(updated);
          setMode({ kind: "list" });
        }}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-medium">Configurations ({draft.configurations.length})</h3>
        {!readOnly && (
          <button
            onClick={() => setMode({ kind: "create" })}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
          >
            Add configuration
          </button>
        )}
      </div>

      {draft.configuration_errors.length > 0 && (
        <div className="rounded border border-amber-900/60 bg-amber-950/30 px-3 py-2 text-sm text-amber-300">
          {draft.configuration_errors.length} configuration entr
          {draft.configuration_errors.length === 1 ? "y" : "ies"} in eval.yaml could not be parsed and are not shown
          below. Fix them in the Advanced tab.
        </div>
      )}

      {draft.configurations.length === 0 ? (
        <div className="rounded-lg border border-neutral-800 py-12 text-center text-neutral-400">
          <p>No configurations yet.</p>
          <p className="mt-1 text-sm">Add at least one configuration to run evaluations.</p>
        </div>
      ) : (
        <ul className="divide-y divide-neutral-800 rounded-lg border border-neutral-800">
          {draft.configurations.map((config) => (
            <li key={config.id} className="flex items-center justify-between gap-4 px-4 py-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-neutral-100">{config.name}</span>
                  {config.role && (
                    <span className="rounded-full bg-neutral-800 px-2 py-0.5 text-xs text-neutral-300">{config.role}</span>
                  )}
                  <span className="text-xs text-neutral-500">×{config.repetitions}</span>
                </div>
                <p className="mt-1 truncate font-mono text-xs text-neutral-500">
                  {formatArgvSummary(config.agent.command)}
                </p>
              </div>
              {!readOnly && (
              <div className="flex shrink-0 items-center gap-2">
                <button
                  onClick={() => setMode({ kind: "edit", configuration: config })}
                  className="rounded border border-neutral-700 px-2.5 py-1 text-xs text-neutral-300 hover:border-neutral-500 transition-colors"
                >
                  Edit
                </button>
                {pendingDeleteId === config.id ? (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-red-400">Delete?</span>
                    <button
                      onClick={() => handleDelete(config.id)}
                      disabled={deleting}
                      className="rounded bg-red-700 px-2 py-1 text-xs text-white hover:bg-red-600 disabled:opacity-50 transition-colors"
                    >
                      {deleting ? "…" : "Confirm"}
                    </button>
                    <button
                      onClick={() => setPendingDeleteId(null)}
                      className="text-xs text-neutral-400 hover:text-neutral-200"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setPendingDeleteId(config.id)}
                    className="rounded border border-neutral-700 px-2.5 py-1 text-xs text-red-400 hover:border-red-700 transition-colors"
                  >
                    Delete
                  </button>
                )}
              </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {deleteError && <p className="text-xs text-red-400">{deleteError}</p>}
    </div>
  );
}
