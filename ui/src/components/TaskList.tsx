"use client";

import { useState } from "react";
import { getMemberName } from "@/lib/member-identity";
import type { ProjectDraft, TaskDraft, TaskEntry } from "@/lib/project-schema";
import { TaskForm } from "./TaskForm";

interface TaskListProps {
  workspaceId: string;
  initialDraft: ProjectDraft;
  /** Archived workspaces are read-only: no add/edit/delete controls. */
  readOnly?: boolean;
}

type Mode = { kind: "list" } | { kind: "create" } | { kind: "edit"; task: TaskDraft };

/** A pending/target delete: by task id when the task parsed, by file path otherwise (F6). */
type DeleteTarget = { kind: "id"; value: string } | { kind: "path"; value: string };

function targetKey(target: DeleteTarget): string {
  return `${target.kind}:${target.value}`;
}

function workspaceTypeOf(entry: TaskEntry): string {
  const ws = entry.task?.workspace as Record<string, unknown> | undefined;
  return typeof ws?.type === "string" ? ws.type : "blank";
}

export function TaskList({ workspaceId, initialDraft, readOnly = false }: TaskListProps) {
  const [draft, setDraft] = useState(initialDraft);
  const [mode, setMode] = useState<Mode>({ kind: "list" });
  const [pendingDeleteKey, setPendingDeleteKey] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function handleDelete(target: DeleteTarget) {
    const member = getMemberName();
    if (!member) {
      setDeleteError("Set your member name first (top-right)");
      return;
    }
    setDeleting(true);
    setDeleteError(null);
    try {
      // Entries whose task body parsed have an id and use the id route;
      // entries with a parse error (task is null) have no id, so they are
      // deleted by their file path instead (F6).
      const url =
        target.kind === "id"
          ? `/api/workspaces/${workspaceId}/project/tasks/${encodeURIComponent(target.value)}`
          : `/api/workspaces/${workspaceId}/project/tasks?path=${encodeURIComponent(target.value)}`;
      const res = await fetch(url, {
        method: "DELETE",
        headers: { "Content-Type": "application/json", "X-Micro-Eval-Member": member },
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || body.error || `HTTP ${res.status}`);
      }
      const updated: ProjectDraft = await res.json();
      setDraft(updated);
      setPendingDeleteKey(null);
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Failed to delete task");
    } finally {
      setDeleting(false);
    }
  }

  if (mode.kind === "create" || mode.kind === "edit") {
    return (
      <TaskForm
        workspaceId={workspaceId}
        existing={mode.kind === "edit" ? mode.task : null}
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
        <h3 className="text-base font-medium">Tasks ({draft.tasks.length})</h3>
        {!readOnly && (
          <button
            onClick={() => setMode({ kind: "create" })}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
          >
            Add task
          </button>
        )}
      </div>

      {draft.tasks.length === 0 ? (
        <div className="rounded-lg border border-neutral-800 py-12 text-center text-neutral-400">
          <p>No tasks yet.</p>
          <p className="mt-1 text-sm">Add at least one task to run evaluations.</p>
        </div>
      ) : (
        <ul className="divide-y divide-neutral-800 rounded-lg border border-neutral-800">
          {draft.tasks.map((entry) => {
            if (entry.error || !entry.task) {
              const target: DeleteTarget = { kind: "path", value: entry.path };
              return (
                <li key={entry.path} className="flex items-center justify-between gap-4 bg-red-950/20 px-4 py-3">
                  <div className="min-w-0">
                    <p className="font-mono text-sm text-red-300">{entry.path}</p>
                    <p className="mt-1 truncate text-xs text-red-400">{entry.error ?? "failed to parse"}</p>
                  </div>
                  {!readOnly && (
                    <DeleteControl
                      target={target}
                      pendingDeleteKey={pendingDeleteKey}
                      deleting={deleting}
                      setPendingDeleteKey={setPendingDeleteKey}
                      onConfirm={handleDelete}
                    />
                  )}
                </li>
              );
            }

            const task = entry.task;
            const target: DeleteTarget = { kind: "id", value: task.id };
            const expectationsCount = task.expectations.length;
            return (
              <li key={entry.path} className="flex items-center justify-between gap-4 px-4 py-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-neutral-100">{task.name}</span>
                    <span className="font-mono text-xs text-neutral-500">{task.id}</span>
                    <span className="rounded-full bg-neutral-800 px-2 py-0.5 text-xs text-neutral-300">
                      {workspaceTypeOf(entry)}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-neutral-500">
                    {expectationsCount === 0
                      ? "no automatic validation"
                      : `${expectationsCount} expectation${expectationsCount === 1 ? "" : "s"}`}
                  </p>
                </div>
                {!readOnly && (
                <div className="flex shrink-0 items-center gap-2">
                  <button
                    onClick={() => setMode({ kind: "edit", task })}
                    className="rounded border border-neutral-700 px-2.5 py-1 text-xs text-neutral-300 hover:border-neutral-500 transition-colors"
                  >
                    Edit
                  </button>
                  <DeleteControl
                    target={target}
                    pendingDeleteKey={pendingDeleteKey}
                    deleting={deleting}
                    setPendingDeleteKey={setPendingDeleteKey}
                    onConfirm={handleDelete}
                  />
                </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {deleteError && <p className="text-xs text-red-400">{deleteError}</p>}
    </div>
  );
}

function DeleteControl({
  target,
  pendingDeleteKey,
  deleting,
  setPendingDeleteKey,
  onConfirm,
}: {
  target: DeleteTarget;
  pendingDeleteKey: string | null;
  deleting: boolean;
  setPendingDeleteKey: (key: string | null) => void;
  onConfirm: (target: DeleteTarget) => void;
}) {
  const key = targetKey(target);
  if (pendingDeleteKey === key) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs text-red-400">Delete?</span>
        <button
          onClick={() => onConfirm(target)}
          disabled={deleting}
          className="rounded bg-red-700 px-2 py-1 text-xs text-white hover:bg-red-600 disabled:opacity-50 transition-colors"
        >
          {deleting ? "…" : "Confirm"}
        </button>
        <button onClick={() => setPendingDeleteKey(null)} className="text-xs text-neutral-400 hover:text-neutral-200">
          Cancel
        </button>
      </div>
    );
  }
  return (
    <button
      onClick={() => setPendingDeleteKey(key)}
      className="rounded border border-neutral-700 px-2.5 py-1 text-xs text-red-400 hover:border-red-700 transition-colors"
    >
      Delete
    </button>
  );
}
