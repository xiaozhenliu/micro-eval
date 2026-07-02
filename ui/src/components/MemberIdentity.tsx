"use client";

// Task 13 (C11): persistent member identity widget shown in the server nav.
// Reads/writes the shared member-identity util only — never touches
// localStorage directly — so this stays in sync with RunEnqueueButton (Task 3)
// and any other consumer of the X-Micro-Eval-Member identity.

import { useState, useEffect } from "react";
import { getMemberName, setMemberName } from "@/lib/member-identity";

export function MemberIdentity() {
  const [name, setName] = useState("");
  const [editing, setEditing] = useState(false);
  const [input, setInput] = useState("");

  useEffect(() => {
    setName(getMemberName());
  }, []);

  function handleSave() {
    const trimmed = input.trim();
    setMemberName(trimmed);
    setName(trimmed);
    setEditing(false);
  }

  if (editing) {
    return (
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSave()}
          placeholder="Your name"
          className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-xs text-neutral-100 placeholder-neutral-600 focus:border-blue-500 focus:outline-none w-28"
          autoFocus
        />
        <button
          onClick={handleSave}
          className="rounded bg-blue-600 px-2 py-1 text-xs font-medium text-white hover:bg-blue-500 transition-colors"
        >
          Save
        </button>
        <button
          onClick={() => setEditing(false)}
          className="text-xs text-neutral-500 hover:text-neutral-300"
        >
          Cancel
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={() => {
        setInput(name);
        setEditing(true);
      }}
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium bg-neutral-800 text-neutral-300 border border-neutral-700 hover:border-neutral-500 transition-colors"
      title="Click to change your name"
    >
      {name || "Set your name"}
    </button>
  );
}
