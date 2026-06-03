"use client";

import { useState, useTransition } from "react";
import type { CellResult } from "@/lib/schema";

interface AnnotationPanelProps {
  runId: string;
  cells: CellResult[];
}

export function AnnotationPanel({ runId, cells }: AnnotationPanelProps) {
  if (cells.length === 0) return null;
  return (
    <section className="mt-8 border border-neutral-800 rounded-lg p-6">
      <h3 className="text-base font-semibold mb-4">Human Evaluation</h3>
      <div className="space-y-4">
        {cells.map((cell) => (
          <EvaluationForm key={cell.cell_id} runId={runId} cell={cell} />
        ))}
      </div>
    </section>
  );
}

function EvaluationForm({ runId, cell }: { runId: string; cell: CellResult }) {
  const [passFail, setPassFail] = useState<"pass" | "fail">(cell.pass_fail ?? "pass");
  const [score, setScore] = useState(cell.score ?? 1);
  const [comment, setComment] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function submit() {
    startTransition(async () => {
      setStatus(null);
      const response = await fetch(`/api/runs/${runId}/cells/${encodeURIComponent(cell.cell_id)}/evaluate`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ pass_fail: passFail, score, scores: {}, comment, evaluator: "human" }),
      });
      if (!response.ok) {
        setStatus("Failed to save evaluation");
        return;
      }
      setStatus("Saved. Refresh to see recomputed decision.");
    });
  }

  return (
    <div className="border-b border-neutral-800/50 pb-4">
      <div className="font-mono text-xs text-neutral-400 mb-3">
        {cell.task_id} / {cell.configuration_id} / rep {cell.repetition}
      </div>
      <div className="grid gap-3 md:grid-cols-[120px_1fr]">
        <label className="text-sm text-neutral-400" htmlFor={`${cell.cell_id}-pass-fail`}>Pass/fail</label>
        <select
          id={`${cell.cell_id}-pass-fail`}
          value={passFail}
          onChange={(event) => setPassFail(event.target.value as "pass" | "fail")}
          className="bg-neutral-900 border border-neutral-700 rounded px-3 py-2 text-sm"
        >
          <option value="pass">pass</option>
          <option value="fail">fail</option>
        </select>

        <label className="text-sm text-neutral-400" htmlFor={`${cell.cell_id}-score`}>Score</label>
        <input
          id={`${cell.cell_id}-score`}
          type="number"
          min={0}
          max={1}
          step={0.1}
          value={score}
          onChange={(event) => setScore(Number(event.target.value))}
          className="bg-neutral-900 border border-neutral-700 rounded px-3 py-2 text-sm"
        />

        <label className="text-sm text-neutral-400" htmlFor={`${cell.cell_id}-comment`}>Comment</label>
        <textarea
          id={`${cell.cell_id}-comment`}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          rows={2}
          className="bg-neutral-900 border border-neutral-700 rounded px-3 py-2 text-sm resize-none"
          placeholder="Why should this cell pass/fail?"
        />
      </div>
      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={submit}
          disabled={isPending}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded text-sm font-medium transition-colors"
        >
          {isPending ? "Saving..." : "Append evaluation"}
        </button>
        {status && <span className="text-xs text-neutral-400">{status}</span>}
      </div>
    </div>
  );
}
