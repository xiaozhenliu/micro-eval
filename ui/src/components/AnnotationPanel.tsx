"use client";

import { useState, useCallback, useMemo, useSyncExternalStore } from "react";

interface Annotation {
  task_id: string;
  score: number;
  notes: string;
}

interface AnnotationPanelProps {
  runId: string;
  tasks: string[];
}

function getStorageKey(runId: string) {
  return `micro-eval-annotations-${runId}`;
}

export function AnnotationPanel({ runId, tasks }: AnnotationPanelProps) {
  return <AnnotationPanelState key={runId} runId={runId} tasks={tasks} />;
}

function getStoredAnnotationJson(runId: string) {
  if (typeof window === "undefined") {
    return null;
  }

  return localStorage.getItem(getStorageKey(runId));
}

function parseAnnotations(stored: string | null): Record<string, Annotation> {
  if (!stored) {
    return {};
  }

  try {
    return JSON.parse(stored);
  } catch {
    // ignore corrupt data
    return {};
  }
}

function subscribeAnnotations(onStoreChange: () => void) {
  window.addEventListener("storage", onStoreChange);
  return () => window.removeEventListener("storage", onStoreChange);
}

function AnnotationPanelState({ runId, tasks }: AnnotationPanelProps) {
  const storedAnnotationJson = useSyncExternalStore(
    subscribeAnnotations,
    () => getStoredAnnotationJson(runId),
    () => null
  );
  const storedAnnotations = useMemo(
    () => parseAnnotations(storedAnnotationJson),
    [storedAnnotationJson]
  );
  const [draftAnnotations, setDraftAnnotations] =
    useState<Record<string, Annotation> | null>(null);
  const annotations = draftAnnotations ?? storedAnnotations;

  const updateAnnotation = useCallback(
    (taskId: string, field: "score" | "notes", value: string | number) => {
      setDraftAnnotations((prev) => {
        const base = prev ?? storedAnnotations;
        const existing = base[taskId] || { task_id: taskId, score: 5, notes: "" };
        return { ...base, [taskId]: { ...existing, [field]: value } };
      });
    },
    [storedAnnotations]
  );

  const save = useCallback(() => {
    localStorage.setItem(getStorageKey(runId), JSON.stringify(annotations));
  }, [runId, annotations]);

  const exportJson = useCallback(() => {
    const blob = new Blob([JSON.stringify(Object.values(annotations), null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `annotations-${runId}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [annotations, runId]);

  return (
    <div className="mt-8 border border-neutral-800 rounded-lg p-6">
      <h3 className="text-base font-semibold mb-4">Annotations</h3>
      <div className="space-y-4">
        {tasks.map((taskId) => {
          const ann = annotations[taskId] || { task_id: taskId, score: 5, notes: "" };
          return (
            <div key={taskId} className="border-b border-neutral-800/50 pb-4">
              <label className="block font-mono text-xs text-neutral-400 mb-2">
                {taskId}
              </label>
              <div className="flex items-center gap-3 mb-2">
                <span className="text-xs text-neutral-500 w-16">
                  Score: {ann.score}
                </span>
                <input
                  type="range"
                  min={1}
                  max={10}
                  value={ann.score}
                  onChange={(e) => updateAnnotation(taskId, "score", Number(e.target.value))}
                  className="flex-1"
                  aria-label={`Score for ${taskId}`}
                />
              </div>
              <textarea
                value={ann.notes}
                onChange={(e) => updateAnnotation(taskId, "notes", e.target.value)}
                placeholder="Notes..."
                rows={2}
                className="w-full bg-neutral-900 border border-neutral-700 rounded px-3 py-2 text-sm resize-none focus:outline-none focus:border-blue-500"
                aria-label={`Notes for ${taskId}`}
              />
            </div>
          );
        })}
      </div>
      <div className="flex gap-3 mt-4">
        <button
          onClick={save}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm font-medium transition-colors"
        >
          Save
        </button>
        <button
          onClick={exportJson}
          className="px-4 py-2 bg-neutral-800 hover:bg-neutral-700 rounded text-sm font-medium transition-colors"
        >
          Export JSON
        </button>
      </div>
    </div>
  );
}
