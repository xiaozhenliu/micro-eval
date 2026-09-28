"use client";

import { useMemo, useState } from "react";
import { getMemberName, setMemberName as persistMemberName } from "@/lib/member-identity";
import { ConfigurationInputSchema, type ConfigurationDraft, type ProjectDraft } from "@/lib/project-schema";
import {
  PRESETS,
  DEFAULT_TIMEOUT_S,
  buildAgentSpec,
  slugifyId,
  parseEnvLines,
  detectPreset,
  formatCommandPreview,
  type PresetId,
} from "@/lib/agent-presets";

interface ConfigurationFormProps {
  workspaceId: string;
  existing: ConfigurationDraft | null;
  onCancel: () => void;
  onSaved: (draft: ProjectDraft) => void;
}

interface FieldError {
  path: string;
  message: string;
}

type Role = "none" | "baseline" | "candidate";

function envToText(env: Record<string, string>): string {
  return Object.entries(env)
    .map(([k, v]) => `${k}=${v}`)
    .join("\n");
}

function commandToText(command: string[]): string {
  return command.join("\n");
}

/** Small numeric stepper — used for repetitions and max turns (enum-like small integers). */
function Stepper({
  value,
  min,
  onChange,
  id,
}: {
  value: number;
  min: number;
  onChange: (next: number) => void;
  id?: string;
}) {
  return (
    <div className="inline-flex items-center rounded border border-neutral-700 bg-neutral-900">
      <button
        type="button"
        onClick={() => onChange(Math.max(min, value - 1))}
        className="px-2.5 py-1.5 text-neutral-400 hover:text-neutral-100"
        aria-label="decrease"
      >
        −
      </button>
      <input
        id={id}
        type="number"
        min={min}
        value={value}
        onChange={(e) => {
          const next = parseInt(e.target.value, 10);
          onChange(Number.isNaN(next) ? min : Math.max(min, next));
        }}
        className="w-14 border-x border-neutral-700 bg-transparent px-2 py-1.5 text-center text-sm text-neutral-100 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
      />
      <button
        type="button"
        onClick={() => onChange(value + 1)}
        className="px-2.5 py-1.5 text-neutral-400 hover:text-neutral-100"
        aria-label="increase"
      >
        +
      </button>
    </div>
  );
}

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

const inputClass =
  "w-full rounded border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 placeholder-neutral-600 focus:border-blue-500 focus:outline-none";
const labelClass = "block text-sm font-medium text-neutral-300 mb-1.5";

export function ConfigurationForm({ workspaceId, existing, onCancel, onSaved }: ConfigurationFormProps) {
  const detected = existing ? detectPreset(existing.agent) : null;

  const [name, setName] = useState(existing?.name ?? "");
  const [id, setId] = useState(existing?.id ?? "");
  const [idTouched, setIdTouched] = useState(Boolean(existing));
  const [role, setRole] = useState<Role>((existing?.role as Role) ?? "none");
  const [repetitions, setRepetitions] = useState(existing?.repetitions ?? 1);
  const [presetId, setPresetId] = useState<PresetId>(detected?.preset ?? "claude-code");
  const [model, setModel] = useState(detected?.model ?? "");
  const [maxTurns, setMaxTurns] = useState(detected?.maxTurns ?? 10);
  const [timeoutS, setTimeoutS] = useState(existing?.agent.timeout_s ?? DEFAULT_TIMEOUT_S[detected?.preset ?? "claude-code"]);
  const [timeoutTouched, setTimeoutTouched] = useState(Boolean(existing));
  const [customArgvLines, setCustomArgvLines] = useState(
    existing && (detected?.preset ?? "custom") === "custom" ? commandToText(existing.agent.command) : "",
  );
  const [customInputMode, setCustomInputMode] = useState<"stdin" | "file">(existing?.agent.input_mode ?? "stdin");
  const [customOutputMode, setCustomOutputMode] = useState<"stdout" | "file" | "directory">(
    existing?.agent.output_mode ?? "stdout",
  );
  const [envText, setEnvText] = useState(existing ? envToText(existing.agent.env) : "");
  const [secretsText, setSecretsText] = useState(existing ? existing.agent.required_secrets.join("\n") : "");

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

  function handlePresetChange(next: PresetId) {
    setPresetId(next);
    if (!timeoutTouched) setTimeoutS(DEFAULT_TIMEOUT_S[next]);
  }

  const previewCommand = useMemo(() => {
    const envParsed = parseEnvLines(envText);
    const requiredSecrets = secretsText
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l !== "");
    const agent = buildAgentSpec(presetId, {
      name: name.trim() || "agent",
      model: model.trim() || undefined,
      maxTurns,
      timeoutS,
      customArgvLines,
      customInputMode,
      customOutputMode,
      env: envParsed.env,
      requiredSecrets,
    });
    return formatCommandPreview(agent.command);
  }, [presetId, name, model, maxTurns, timeoutS, customArgvLines, customInputMode, customOutputMode, envText, secretsText]);

  function buildPayload() {
    const envParsed = parseEnvLines(envText);
    if (envParsed.errors.length > 0) {
      return { errors: envParsed.errors.map((message) => ({ path: "agent.env", message })) };
    }

    const requiredSecrets = secretsText
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l !== "");

    const agent = buildAgentSpec(presetId, {
      name: name.trim(),
      model: model.trim() || undefined,
      maxTurns,
      timeoutS,
      customArgvLines,
      customInputMode,
      customOutputMode,
      env: envParsed.env,
      requiredSecrets,
    });

    const payload = {
      id,
      name: name.trim(),
      agent,
      repetitions,
      role: role === "none" ? null : role,
      skills_profile: existing?.skills_profile ?? {},
      parameters: existing?.parameters ?? {},
    };

    const parsed = ConfigurationInputSchema.safeParse(payload);
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
      const res = await fetch(`/api/workspaces/${workspaceId}/project/configurations`, {
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
      setSubmitError(err instanceof Error ? err.message : "Failed to save configuration");
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
  const timeoutError = errorFor("agent.timeout_s");
  const commandError = errorFor("agent.command");
  const otherErrors = fieldErrors.filter(
    (e) => !["id", "name", "agent.timeout_s", "agent.command"].includes(e.path) && !e.path.startsWith("agent.env"),
  );
  const envErrors = fieldErrors.filter((e) => e.path.startsWith("agent.env"));

  return (
    <form onSubmit={handleSubmit} className="max-w-2xl space-y-5">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-medium">{existing ? "Edit configuration" : "Add configuration"}</h3>
        <button type="button" onClick={onCancel} className="text-sm text-neutral-400 hover:text-neutral-200">
          Cancel
        </button>
      </div>

      <div>
        <label htmlFor="config-name" className={labelClass}>
          Name <span className="text-red-400">*</span>
        </label>
        <input
          id="config-name"
          type="text"
          value={name}
          onChange={(e) => handleNameChange(e.target.value)}
          placeholder="e.g. Claude Code baseline"
          className={inputClass}
        />
        {nameError && <p className="mt-1 text-xs text-red-400">{nameError}</p>}
      </div>

      <div>
        <label htmlFor="config-id" className={labelClass}>
          Id <span className="text-red-400">*</span>
        </label>
        <input
          id="config-id"
          type="text"
          value={id}
          onChange={(e) => handleIdChange(e.target.value)}
          placeholder="e.g. claude-baseline"
          readOnly={Boolean(existing)}
          aria-readonly={Boolean(existing)}
          className={`${inputClass} font-mono ${existing ? "cursor-not-allowed opacity-60" : ""}`}
        />
        {existing && (
          <p className="mt-1 text-xs text-neutral-500">
            Id cannot change while editing; create a new configuration instead.
          </p>
        )}
        {idError && <p className="mt-1 text-xs text-red-400">{idError}</p>}
      </div>

      <div>
        <label className={labelClass}>Role</label>
        <SegmentedControl
          value={role}
          onChange={setRole}
          options={[
            { value: "none", label: "None" },
            { value: "baseline", label: "Baseline" },
            { value: "candidate", label: "Candidate" },
          ]}
        />
      </div>

      <div>
        <label htmlFor="config-repetitions" className={labelClass}>
          Repetitions
        </label>
        <Stepper id="config-repetitions" value={repetitions} min={1} onChange={setRepetitions} />
      </div>

      <div>
        <label htmlFor="config-preset" className={labelClass}>
          Agent preset
        </label>
        <select
          id="config-preset"
          value={presetId}
          onChange={(e) => handlePresetChange(e.target.value as PresetId)}
          className={inputClass}
        >
          {PRESETS.map((preset) => (
            <option key={preset.id} value={preset.id}>
              {preset.label}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-neutral-500">{PRESETS.find((p) => p.id === presetId)?.description}</p>
      </div>

      {(presetId === "claude-code" || presetId === "codex-cli") && (
        <div>
          <label htmlFor="config-model" className={labelClass}>
            Model
          </label>
          <input
            id="config-model"
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="leave empty for the CLI default"
            className={inputClass}
          />
        </div>
      )}

      {presetId === "claude-code" && (
        <div>
          <label htmlFor="config-max-turns" className={labelClass}>
            Max turns
          </label>
          <Stepper id="config-max-turns" value={maxTurns} min={1} onChange={setMaxTurns} />
        </div>
      )}

      {presetId === "custom" && (
        <>
          <div>
            <label htmlFor="config-argv" className={labelClass}>
              Argv <span className="text-red-400">*</span>
            </label>
            <textarea
              id="config-argv"
              value={customArgvLines}
              onChange={(e) => setCustomArgvLines(e.target.value)}
              rows={4}
              spellCheck={false}
              placeholder={"one argument per line, e.g.\npython\nagent.py"}
              className={`${inputClass} font-mono resize-y`}
            />
            {commandError && <p className="mt-1 text-xs text-red-400">{commandError}</p>}
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="config-input-mode" className={labelClass}>
                Input mode
              </label>
              <select
                id="config-input-mode"
                value={customInputMode}
                onChange={(e) => setCustomInputMode(e.target.value as "stdin" | "file")}
                className={inputClass}
              >
                <option value="stdin">stdin</option>
                <option value="file">file</option>
              </select>
            </div>
            <div>
              <label htmlFor="config-output-mode" className={labelClass}>
                Output mode
              </label>
              <select
                id="config-output-mode"
                value={customOutputMode}
                onChange={(e) => setCustomOutputMode(e.target.value as "stdout" | "file" | "directory")}
                className={inputClass}
              >
                <option value="stdout">stdout</option>
                <option value="file">file</option>
                <option value="directory">directory</option>
              </select>
            </div>
          </div>
        </>
      )}

      <div>
        <label htmlFor="config-timeout" className={labelClass}>
          Timeout (seconds)
        </label>
        <input
          id="config-timeout"
          type="number"
          min={1}
          value={timeoutS}
          onChange={(e) => {
            const next = Number(e.target.value);
            setTimeoutS(Number.isNaN(next) ? timeoutS : next);
            setTimeoutTouched(true);
          }}
          className={inputClass}
        />
        {timeoutError && <p className="mt-1 text-xs text-red-400">{timeoutError}</p>}
      </div>

      <div>
        <label htmlFor="config-env" className={labelClass}>
          Environment variables
        </label>
        <textarea
          id="config-env"
          value={envText}
          onChange={(e) => setEnvText(e.target.value)}
          rows={3}
          spellCheck={false}
          placeholder={"one KEY=VALUE per line"}
          className={`${inputClass} font-mono resize-y`}
        />
        {envErrors.map((e, i) => (
          <p key={i} className="mt-1 text-xs text-red-400">
            {e.message}
          </p>
        ))}
      </div>

      <div>
        <label htmlFor="config-secrets" className={labelClass}>
          Required secrets
        </label>
        <textarea
          id="config-secrets"
          value={secretsText}
          onChange={(e) => setSecretsText(e.target.value)}
          rows={2}
          spellCheck={false}
          placeholder={"one MICRO_EVAL_SECRET_* name per line"}
          className={`${inputClass} font-mono resize-y`}
        />
        <p className="mt-1 text-xs text-neutral-500">
          Only the secret name is sent — never the value. The value must already be set in the server&apos;s
          environment.
        </p>
      </div>

      <div>
        <label className={labelClass}>Command (preview)</label>
        <p className="rounded border border-neutral-800 bg-neutral-950 px-3 py-2 font-mono text-xs text-neutral-400 break-all">
          {previewCommand || "(empty)"}
        </p>
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
          {saving ? "Saving…" : "Save configuration"}
        </button>
        <button type="button" onClick={onCancel} className="text-sm text-neutral-400 hover:text-neutral-200 transition-colors">
          Cancel
        </button>
      </div>
    </form>
  );
}
