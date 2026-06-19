"use client";

import { useState } from "react";

interface ConfigEditorProps {
  workspaceId: string;
  initialContent: string;
}

export function ConfigEditor({ workspaceId, initialContent }: ConfigEditorProps) {
  const [content, setContent] = useState(initialContent);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<{ kind: "success" | "error"; message: string } | null>(null);

  async function handleSave() {
    setSaving(true);
    setStatus(null);

    try {
      const res = await fetch(`/api/workspaces/${workspaceId}/config`, {
        method: "PUT",
        headers: { "Content-Type": "application/yaml" },
        body: content,
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
      <textarea
        value={content}
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
          disabled={saving}
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
