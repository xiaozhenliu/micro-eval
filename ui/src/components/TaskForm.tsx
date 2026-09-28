"use client";

import { useState } from "react";
import { getMemberName, setMemberName as persistMemberName } from "@/lib/member-identity";
import { TaskInputSchema, type TaskDraft, type ProjectDraft, type ExpectationInput } from "@/lib/project-schema";
import { slugifyId } from "@/lib/agent-presets";

interface TaskFormProps {
  workspaceId: string;
  existing: TaskDraft | null;
  onCancel: () => void;
  onSaved: (draft: ProjectDraft) => void;
}

interface FieldError {
  path: string;
  message: string;
}

type ExpectationType = "contains" | "exit_code" | "file_exists" | "command";
const KNOWN_EXPECTATION_TYPES: ReadonlySet<string> = new Set(["contains", "exit_code", "file_exists", "command"]);

function isKnownExpectation(exp: Record<string, unknown>): boolean {
  return typeof exp.type !== "string" || KNOWN_EXPECTATION_TYPES.has(exp.type);
}
type WorkspaceType = "blank" | "files" | "git_repo";

interface ExpectationRow {
  key: string;
  type: ExpectationType;
  value: string; // contains value, or exit_code as text
  stream: "output" | "stdout" | "stderr";
  path: string; // file_exists
  argvLines: string; // command argv, one per line
  cwd: string; // command cwd
  timeoutS: number; // command timeout
}

let rowKeySeq = 0;
function newRowKey(): string {
  rowKeySeq += 1;
  return `row-${rowKeySeq}`;
}

function emptyRow(type: ExpectationType = "contains"): ExpectationRow {
  return {
    key: newRowKey(),
    type,
    value: "",
    stream: "output",
    path: "",
    argvLines: "",
    cwd: "",
    timeoutS: 30,
  };
}

function expectationToRow(exp: Record<string, unknown>): ExpectationRow {
  const type = (typeof exp.type === "string" ? exp.type : "contains") as ExpectationType;
  const value = exp.value === null || exp.value === undefined ? "" : String(exp.value);
  const stream = (typeof exp.stream === "string" ? exp.stream : "output") as ExpectationRow["stream"];
  // N6: ExpectationSpec.validate_expectation copies `path` into `value` when
  // `value` is unset, so a file_exists expectation round-tripped through the
  // backend may only carry the path in `value`. Fall back to `value` so
  // editing an existing row never shows an empty path field.
  const path = typeof exp.path === "string" ? exp.path : value;
  const command = Array.isArray(exp.command) ? (exp.command as unknown[]).map(String) : [];
  const cwd = typeof exp.cwd === "string" ? exp.cwd : "";
  const timeoutS = typeof exp.timeout_s === "number" ? exp.timeout_s : 30;
  return { key: newRowKey(), type, value, stream, path, argvLines: command.join("\n"), cwd, timeoutS };
}

function rowToExpectation(row: ExpectationRow): ExpectationInput {
  switch (row.type) {
    case "contains":
      return {
        type: "contains",
        value: row.value,
        path: null,
        stream: row.stream,
        command: null,
        cwd: null,
        timeout_s: 30,
      };
    case "exit_code": {
      const parsed = parseInt(row.value, 10);
      return {
        type: "exit_code",
        value: Number.isNaN(parsed) ? 0 : parsed,
        path: null,
        stream: "output",
        command: null,
        cwd: null,
        timeout_s: 30,
      };
    }
    case "file_exists":
      // N6: send both `path` and `value` set to the same string. Pydantic's
      // ExpectationSpec normalises path -> value anyway, but sending both
      // explicitly means a round trip never depends on that normalisation.
      return {
        type: "file_exists",
        value: row.path,
        path: row.path,
        stream: "output",
        command: null,
        cwd: null,
        timeout_s: 30,
      };
    case "command": {
      const argv = row.argvLines
        .split("\n")
        .map((l) => l.replace(/\r$/, ""))
        .filter((l) => l.trim() !== "");
      return {
        type: "command",
        value: null,
        path: null,
        stream: "output",
        command: argv,
        cwd: row.cwd.trim() || null,
        timeout_s: row.timeoutS,
      };
    }
  }
}

function extractWorkspace(existing: TaskDraft | null): {
  type: WorkspaceType;
  gitPath: string;
  gitRef: string;
  filesText: string;
} {
  const ws = (existing?.workspace ?? {}) as Record<string, unknown>;
  const type = (typeof ws.type === "string" ? ws.type : "blank") as WorkspaceType;
  const gitPath = typeof ws.path === "string" ? ws.path : "";
  const gitRef = typeof ws.ref === "string" ? ws.ref : "";
  const files = Array.isArray(ws.files) ? (ws.files as unknown[]).map(String) : [];
  return { type, gitPath, gitRef, filesText: files.join("\n") };
}

/** Shallow-copies `obj` without the given keys, without leaving unused bindings around. */
function omitKeys(obj: Record<string, unknown>, keys: string[]): Record<string, unknown> {
  const result: Record<string, unknown> = { ...obj };
  for (const key of keys) delete result[key];
  return result;
}

/**
 * True when `existing` carries workspace/task fields the basic form below
 * does not expose (isolation_level, trust_level, network_policy, fixtures,
 * toolchain, setup commands, or the conversational scenario/expected_outcome
 * /user_description fields). Used to warn that saving from this form keeps
 * them as-is rather than silently dropping them (F7).
 */
function hasAdvancedFields(existing: TaskDraft | null): boolean {
  if (!existing) return false;
  const ws = (existing.workspace ?? {}) as Record<string, unknown>;
  const isolationLevel = typeof ws.isolation_level === "string" ? ws.isolation_level : null;
  const trustLevel = typeof ws.trust_level === "string" ? ws.trust_level : null;
  const hasNetworkPolicy = ws.network_policy !== null && ws.network_policy !== undefined;
  const hasFixtures = Array.isArray(ws.fixtures) && ws.fixtures.length > 0;
  const hasToolchain = ws.toolchain !== null && ws.toolchain !== undefined;
  const hasSetup = Array.isArray(ws.setup) && ws.setup.length > 0;
  const advancedWorkspace =
    (isolationLevel !== null && isolationLevel !== "logical") ||
    (trustLevel !== null && trustLevel !== "trusted") ||
    hasNetworkPolicy ||
    hasFixtures ||
    hasToolchain ||
    hasSetup;
  const existingRecord = existing as unknown as Record<string, unknown>;
  const advancedTask = Boolean(
    existingRecord.scenario || existingRecord.expected_outcome || existingRecord.user_description,
  );
  return advancedWorkspace || advancedTask;
}

const inputClass =
  "w-full rounded border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 placeholder-neutral-600 focus:border-blue-500 focus:outline-none";
const labelClass = "block text-sm font-medium text-neutral-300 mb-1.5";

function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (next: T) => void;
}) {
  return (
    <div className="inline-flex rounded border border-neutral-700 bg-neutral-900 p-0.5">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          aria-pressed={value === opt.value}
          onClick={() => onChange(opt.value)}
          className={`rounded px-3 py-1 text-sm transition-colors ${
            value === opt.value ? "bg-blue-600 text-white" : "text-neutral-400 hover:text-neutral-100"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export function TaskForm({ workspaceId, existing, onCancel, onSaved }: TaskFormProps) {
  const initialWorkspace = extractWorkspace(existing);

  // N5: existing.rubric may be a structured RubricSpec object ({text,
  // dimensions}) rather than free text. The basic form only edits free-text
  // rubrics, so when the existing value is structured it must stay
  // untouched in the submitted payload — editing a task must never silently
  // downgrade a structured rubric to plain text.
  const structuredRubric =
    existing && existing.rubric !== null && typeof existing.rubric === "object"
      ? (existing.rubric as { text?: unknown; dimensions?: unknown })
      : null;

  const [name, setName] = useState(existing?.name ?? "");
  const [id, setId] = useState(existing?.id ?? "");
  const [idTouched, setIdTouched] = useState(Boolean(existing));
  const [description, setDescription] = useState(existing?.description ?? "");
  const [prompt, setPrompt] = useState(existing?.input_payload ?? "");
  const [expectedOutput, setExpectedOutput] = useState(existing?.expected_output ?? "");
  const [expectations, setExpectations] = useState<ExpectationRow[]>(
    existing && existing.expectations.length > 0
      ? existing.expectations
          .filter((e) => isKnownExpectation(e as Record<string, unknown>))
          .map((e) => expectationToRow(e as Record<string, unknown>))
      : [],
  );
  // Expectations of a type this form cannot edit are preserved verbatim and
  // re-sent with the payload (round-13 review, 2026-09-13).
  const passthroughExpectations = (existing?.expectations ?? []).filter(
    (e) => !isKnownExpectation(e as Record<string, unknown>),
  ) as ExpectationInput[];
  const [workspaceType, setWorkspaceType] = useState<WorkspaceType>(initialWorkspace.type);
  const [gitPath, setGitPath] = useState(initialWorkspace.gitPath);
  const [gitRef, setGitRef] = useState(initialWorkspace.gitRef);
  const [filesText, setFilesText] = useState(initialWorkspace.filesText);
  const [rubric, setRubric] = useState(typeof existing?.rubric === "string" ? existing.rubric : "");
  const [tagsText, setTagsText] = useState(existing?.tags.join(", ") ?? "");

  const [fieldErrors, setFieldErrors] = useState<FieldError[]>([]);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [showNameInput, setShowNameInput] = useState(false);
  const [nameDraft, setNameDraft] = useState("");

  function errorFor(path: string): string | undefined {
    return fieldErrors.find((e) => e.path === path)?.message;
  }

  function handleNameChange(next: string) {
    setName(next);
    if (!idTouched) setId(slugifyId(next));
  }

  function handleIdChange(next: string) {
    setId(next);
    setIdTouched(true);
  }

  function addExpectation() {
    setExpectations((rows) => [...rows, emptyRow()]);
  }

  function removeExpectation(key: string) {
    setExpectations((rows) => rows.filter((r) => r.key !== key));
  }

  function updateExpectation(key: string, patch: Partial<ExpectationRow>) {
    setExpectations((rows) => rows.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }

  function buildPayload() {
    const existingWorkspaceRaw = (existing?.workspace ?? {}) as Record<string, unknown>;
    const tags = tagsText
      .split(",")
      .map((t) => t.trim())
      .filter((t) => t !== "");

    // Only the fields this basic form actually edits. Advanced workspace
    // fields (isolation_level, trust_level, network_policy, fixtures,
    // toolchain, setup) are not touched here; they are carried over from
    // `existing.workspace` below so editing a task never drops them (F7).
    // A `files` workspace may name its source directory in `path` instead
    // of `files`; this form does not edit it, so keep it (round-16 review).
    const existingFilesPath =
      workspaceType === "files" && typeof existingWorkspaceRaw.path === "string" ? existingWorkspaceRaw.path : null;
    const formWorkspace = {
      type: workspaceType,
      path: workspaceType === "git_repo" ? gitPath.trim() || null : existingFilesPath,
      ref: workspaceType === "git_repo" ? gitRef.trim() || null : null,
      files:
        workspaceType === "files"
          ? filesText
              .split("\n")
              .map((l) => l.trim())
              .filter((l) => l !== "")
          : [],
    };
    const workspace = { setup: [] as string[][], ...existingWorkspaceRaw, ...formWorkspace };

    const formFields = {
      id,
      name: name.trim(),
      description: description.trim(),
      input_payload: prompt,
      expected_output: expectedOutput.trim() || null,
      // N5: keep a structured rubric untouched; only a string/null existing
      // rubric is controlled by the textarea's local state.
      rubric: structuredRubric ? (existing!.rubric as TaskDraft["rubric"]) : rubric.trim() || null,
      expectations: [...expectations.map(rowToExpectation), ...passthroughExpectations],
      workspace,
      business_impact_tier: existing?.business_impact_tier ?? 3,
      tags,
    };

    // On edit, start from the existing task (minus revision_id, which is
    // derived server-side from the file's content and must never be sent by
    // the client) so scenario/expected_outcome/user_description and any
    // other field the form does not expose survive the round trip (F7).
    const payload = existing
      ? { ...omitKeys(existing as unknown as Record<string, unknown>, ["schema_version", "revision_id"]), ...formFields }
      : formFields;

    const parsed = TaskInputSchema.safeParse(payload);
    if (!parsed.success) {
      return {
        errors: parsed.error.issues.map((issue) => ({ path: issue.path.join(".") || "form", message: issue.message })),
      };
    }
    return { data: parsed.data };
  }

  async function submitWithMember(member: string) {
    const result = buildPayload();
    if (result.errors) {
      setFieldErrors(result.errors);
      return;
    }
    setFieldErrors([]);
    setSaving(true);
    setSubmitError(null);
    try {
      const res = await fetch(`/api/workspaces/${workspaceId}/project/tasks`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-Micro-Eval-Member": member },
        body: JSON.stringify(result.data),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || body.error || `HTTP ${res.status}`);
      }
      const draft: ProjectDraft = await res.json();
      onSaved(draft);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to save task");
    } finally {
      setSaving(false);
    }
  }

  function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault();
    const result = buildPayload();
    if (result.errors) {
      setFieldErrors(result.errors);
      return;
    }
    setFieldErrors([]);

    const member = getMemberName();
    if (!member) {
      setShowNameInput(true);
      setSubmitError("Set your name first");
      return;
    }
    void submitWithMember(member);
  }

  // Not a nested <form>: browsers drop an inner form element, so the
  // fallback is a plain group whose button and Enter key call this
  // directly (round-12 review, 2026-09-13).
  function handleSaveName(e?: React.SyntheticEvent) {
    e?.preventDefault();
    const trimmed = nameDraft.trim();
    if (!trimmed) return;
    persistMemberName(trimmed);
    setShowNameInput(false);
    setSubmitError(null);
    void submitWithMember(trimmed);
  }

  const idError = errorFor("id");
  const nameError = errorFor("name");
  const promptError = errorFor("input_payload");
  const knownPaths = new Set(["id", "name", "input_payload"]);
  const otherErrors = fieldErrors.filter((e) => !knownPaths.has(e.path));
  const showAdvancedNote = hasAdvancedFields(existing);

  return (
    <form onSubmit={handleSubmit} className="max-w-2xl space-y-5">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-medium">{existing ? "Edit task" : "Add task"}</h3>
        <button type="button" onClick={onCancel} className="text-sm text-neutral-400 hover:text-neutral-200">
          Cancel
        </button>
      </div>

      <div>
        <label htmlFor="task-name" className={labelClass}>
          Name <span className="text-red-400">*</span>
        </label>
        <input
          id="task-name"
          type="text"
          value={name}
          onChange={(e) => handleNameChange(e.target.value)}
          placeholder="e.g. Summarize a changelog"
          className={inputClass}
        />
        {nameError && <p className="mt-1 text-xs text-red-400">{nameError}</p>}
      </div>

      <div>
        <label htmlFor="task-id" className={labelClass}>
          Id <span className="text-red-400">*</span>
        </label>
        <input
          id="task-id"
          type="text"
          value={id}
          onChange={(e) => handleIdChange(e.target.value)}
          placeholder="e.g. summarize-changelog"
          readOnly={Boolean(existing)}
          aria-readonly={Boolean(existing)}
          className={`${inputClass} font-mono ${existing ? "cursor-not-allowed opacity-60" : ""}`}
        />
        {existing && (
          <p className="mt-1 text-xs text-neutral-500">Id cannot change while editing; create a new task instead.</p>
        )}
        {idError && <p className="mt-1 text-xs text-red-400">{idError}</p>}
      </div>

      <div>
        <label htmlFor="task-description" className={labelClass}>
          Description
        </label>
        <textarea
          id="task-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          className={`${inputClass} resize-y`}
        />
      </div>

      <div>
        <label htmlFor="task-prompt" className={labelClass}>
          Prompt <span className="text-red-400">*</span>
        </label>
        <textarea
          id="task-prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={5}
          placeholder="The exact text sent to the agent's stdin."
          className={`${inputClass} font-mono resize-y`}
        />
        {promptError && <p className="mt-1 text-xs text-red-400">{promptError}</p>}
      </div>

      <div>
        <label htmlFor="task-expected-output" className={labelClass}>
          Expected output
        </label>
        <textarea
          id="task-expected-output"
          value={expectedOutput ?? ""}
          onChange={(e) => setExpectedOutput(e.target.value)}
          rows={3}
          placeholder="Optional — shown alongside results for human judgement."
          className={`${inputClass} resize-y`}
        />
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <label className={labelClass}>Expectations</label>
          <button
            type="button"
            onClick={addExpectation}
            className="rounded border border-neutral-700 px-2.5 py-1 text-xs text-neutral-300 hover:border-neutral-500 transition-colors"
          >
            Add expectation
          </button>
        </div>

        {passthroughExpectations.length > 0 && (
          <p className="text-xs text-amber-400">
            {passthroughExpectations.length} expectation{passthroughExpectations.length === 1 ? "" : "s"} of a type this form
            cannot edit ({passthroughExpectations.map((e) => String(e.type)).join(", ")}) will be kept as-is; edit them in
            the task&apos;s YAML file.
          </p>
        )}
        {expectations.length === 0 && passthroughExpectations.length === 0 ? (
          <p className="text-xs text-neutral-500">No automatic validation. The task will rely on human/LLM judgement only.</p>
        ) : (
          <div className="space-y-3">
            {expectations.map((row) => (
              <div key={row.key} className="rounded border border-neutral-800 p-3 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <select
                    value={row.type}
                    onChange={(e) => updateExpectation(row.key, { type: e.target.value as ExpectationType })}
                    className={`${inputClass} max-w-[10rem]`}
                  >
                    <option value="contains">contains</option>
                    <option value="exit_code">exit_code</option>
                    <option value="file_exists">file_exists</option>
                    <option value="command">command</option>
                  </select>
                  <button
                    type="button"
                    onClick={() => removeExpectation(row.key)}
                    className="text-xs text-red-400 hover:text-red-300"
                  >
                    Remove
                  </button>
                </div>

                {row.type === "contains" && (
                  <div className="grid grid-cols-3 gap-2">
                    <input
                      type="text"
                      value={row.value}
                      onChange={(e) => updateExpectation(row.key, { value: e.target.value })}
                      placeholder="text the output must contain"
                      className={`${inputClass} col-span-2`}
                    />
                    <select
                      value={row.stream}
                      onChange={(e) => updateExpectation(row.key, { stream: e.target.value as ExpectationRow["stream"] })}
                      className={inputClass}
                    >
                      <option value="output">output</option>
                      <option value="stdout">stdout</option>
                      <option value="stderr">stderr</option>
                    </select>
                  </div>
                )}

                {row.type === "exit_code" && (
                  <input
                    type="number"
                    value={row.value}
                    onChange={(e) => updateExpectation(row.key, { value: e.target.value })}
                    placeholder="expected exit code, e.g. 0"
                    className={inputClass}
                  />
                )}

                {row.type === "file_exists" && (
                  <input
                    type="text"
                    value={row.path}
                    onChange={(e) => updateExpectation(row.key, { path: e.target.value })}
                    placeholder="path relative to the workspace"
                    className={inputClass}
                  />
                )}

                {row.type === "command" && (
                  <div className="space-y-2">
                    <textarea
                      value={row.argvLines}
                      onChange={(e) => updateExpectation(row.key, { argvLines: e.target.value })}
                      rows={2}
                      spellCheck={false}
                      placeholder={"one argument per line, e.g.\ntest\n-f\noutput.txt"}
                      className={`${inputClass} font-mono resize-y`}
                    />
                    <div className="grid grid-cols-2 gap-2">
                      <input
                        type="text"
                        value={row.cwd}
                        onChange={(e) => updateExpectation(row.key, { cwd: e.target.value })}
                        placeholder="workspace root; or {output_dir}"
                        className={inputClass}
                      />
                      <input
                        type="number"
                        value={row.timeoutS}
                        onChange={(e) =>
                          updateExpectation(row.key, { timeoutS: Number(e.target.value) || row.timeoutS })
                        }
                        placeholder="timeout (s)"
                        className={inputClass}
                      />
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <label className={labelClass}>Workspace</label>
        <SegmentedControl
          value={workspaceType}
          onChange={setWorkspaceType}
          options={[
            { value: "blank", label: "Blank" },
            { value: "files", label: "Files" },
            { value: "git_repo", label: "Git repo" },
          ]}
        />
        {showAdvancedNote && (
          <p className="mt-2 text-xs text-neutral-500">
            Advanced workspace settings are kept as-is; edit them in the task&apos;s YAML file.
          </p>
        )}
      </div>

      {workspaceType === "files" && (
        <div>
          <label htmlFor="task-files" className={labelClass}>
            Files
          </label>
          <textarea
            id="task-files"
            value={filesText}
            onChange={(e) => setFilesText(e.target.value)}
            rows={3}
            spellCheck={false}
            placeholder={"one path per line"}
            className={`${inputClass} font-mono resize-y`}
          />
          {typeof (existing?.workspace as Record<string, unknown> | undefined)?.path === "string" && (
            <p className="mt-1 text-xs text-neutral-500">
              Source directory <span className="font-mono">{String((existing?.workspace as Record<string, unknown>).path)}</span> is
              kept as-is; change it in the task&apos;s YAML file.
            </p>
          )}
        </div>
      )}

      {workspaceType === "git_repo" && (
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor="task-git-path" className={labelClass}>
              Repo path
            </label>
            <input
              id="task-git-path"
              type="text"
              value={gitPath}
              onChange={(e) => setGitPath(e.target.value)}
              placeholder="leave empty for this project"
              className={inputClass}
            />
          </div>
          <div>
            <label htmlFor="task-git-ref" className={labelClass}>
              Ref
            </label>
            <input
              id="task-git-ref"
              type="text"
              value={gitRef}
              onChange={(e) => setGitRef(e.target.value)}
              placeholder="e.g. main"
              className={inputClass}
            />
          </div>
        </div>
      )}

      <div>
        <label htmlFor="task-rubric" className={labelClass}>
          Rubric
        </label>
        <textarea
          id="task-rubric"
          value={structuredRubric ? (typeof structuredRubric.text === "string" ? structuredRubric.text : "") : rubric}
          onChange={(e) => {
            if (!structuredRubric) setRubric(e.target.value);
          }}
          disabled={Boolean(structuredRubric)}
          rows={3}
          placeholder="Optional — free text scoring guidance for a human or LLM judge."
          className={`${inputClass} resize-y ${structuredRubric ? "cursor-not-allowed opacity-60" : ""}`}
        />
        {structuredRubric && (
          <p className="mt-1 text-xs text-neutral-500">Structured rubric; edit it in the task&apos;s YAML file.</p>
        )}
      </div>

      <div>
        <label htmlFor="task-tags" className={labelClass}>
          Tags
        </label>
        <input
          id="task-tags"
          type="text"
          value={tagsText}
          onChange={(e) => setTagsText(e.target.value)}
          placeholder="comma separated, e.g. smoke, regression"
          className={inputClass}
        />
      </div>

      {otherErrors.length > 0 && (
        <div className="rounded border border-red-900/60 bg-red-950/30 px-3 py-2 text-sm text-red-300">
          <ul className="list-disc space-y-0.5 pl-4">
            {otherErrors.map((e, i) => (
              <li key={i}>
                {e.path}: {e.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {submitError && <p className="text-sm text-red-400">{submitError}</p>}

      {showNameInput && (
        <div role="group" aria-label="Your name" className="flex items-center gap-2">
          <input
            type="text"
            autoFocus
            value={nameDraft}
            onChange={(e) => setNameDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSaveName(e);
            }}
            placeholder="Your name"
            className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-sm text-neutral-100"
          />
          <button
            type="button"
            onClick={() => handleSaveName()}
            className="rounded bg-neutral-700 px-2 py-1 text-xs font-medium text-white hover:bg-neutral-600 transition-colors"
          >
            Save &amp; Submit
          </button>
        </div>
      )}

      <div className="flex items-center gap-3 pt-2">
        <button
          type="submit"
          disabled={saving}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? "Saving…" : "Save task"}
        </button>
        <button type="button" onClick={onCancel} className="text-sm text-neutral-400 hover:text-neutral-200 transition-colors">
          Cancel
        </button>
      </div>
    </form>
  );
}
