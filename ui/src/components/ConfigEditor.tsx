"use client";

import { useState } from "react";
import { getMemberName } from "@/lib/member-identity";

interface ConfigEditorProps {
  workspaceId: string;
  initialContent: string;
  /** True when `initialContent` has declared secret values replaced by `[REDACTED:<NAME>]` (N1). */
  redacted?: boolean;
  /** True when eval.yaml could not be read; saving is disabled so an empty editor never overwrites it. */
  readFailed?: boolean;
  /** Archived workspaces are read-only: the editor shows the file but cannot save. */
  readOnly?: boolean;
}

export function ConfigEditor({ workspaceId, initialContent, redacted = false, readFailed = false, readOnly = false }: ConfigEditorProps) {
  const [content, setContent] = useState(initialContent);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<{ kind: "success" | "error"; message: string } | null>(null);

  async function handleSave() {
    setSaving(true);
    setStatus(null);

    try {
      const member = getMemberName();
      if (!member) {
        setStatus({ kind: "error", message: "Set your member name first (top-right)" });
        setSaving(false);
        return;
      }
      const res = await fetch(`/api/workspaces/${workspaceId}/config`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "X-Micro-Eval-Member": member,
        },
        body: JSON.stringify({ content }),
      });

      if (!res.ok) {
        const body = await res.text();
        throw new Error(body || `HTTP ${res.status}`);
      }

      setStatus({ kind: "success", message: "Saved" });
    } catch (err) {
      setStatus({
        kind: "error",
        message: err instanceof Error ? err.message : "Failed to save",
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {readFailed && (
        <p className="text-xs text-red-400">
          eval.yaml could not be read, so saving is disabled: an empty editor must never overwrite the file.
        </p>
      )}
      {redacted && (
        <p className="text-xs text-amber-400">
          Declared secret values are shown as [REDACTED:NAME]; saving a placeholder is rejected.
        </p>
      )}
      <textarea
        value={content}
        readOnly={readOnly}
        aria-readonly={readOnly}
        onChange={(e) => {
          setContent(e.target.value);
          setStatus(null);
        }}
        spellCheck={false}
        rows={20}
        className="w-full font-mono text-sm bg-neutral-900 border border-neutral-800 rounded-lg p-4 text-neutral-100 resize-y focus:outline-none focus:border-neutral-600 transition-colors"
      />
      <div className="flex items-center gap-4">
        <button
          onClick={handleSave}
          disabled={saving || readFailed || readOnly}
          className="inline-flex items-center gap-2 px-4 py-2 rounded bg-neutral-700 text-white text-sm font-medium hover:bg-neutral-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {saving && (
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          )}
          {saving ? "Saving…" : "Save"}
        </button>
        {status && (
          <p className={`text-xs ${status.kind === "success" ? "text-green-400" : "text-red-400"}`}>
            {status.message}
          </p>
        )}
      </div>
    </div>
  );
}
