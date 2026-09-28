/**
 * Pure helpers for the Configurations form (GRO-551): agent preset argv
 * construction, id slugification, env-line parsing, and preset detection
 * for editing existing configurations. No I/O, no React — fully unit
 * testable and shared between ConfigurationForm and ConfigurationList.
 */
import type { AgentSpecInput } from "./project-schema";

export type PresetId = "claude-code" | "codex-cli" | "echo" | "custom";

export interface PresetInfo {
  id: PresetId;
  label: string;
  description: string;
}

export const PRESETS: PresetInfo[] = [
  {
    id: "claude-code",
    label: "Claude Code",
    description: "claude -p with acceptEdits permissions, reads the prompt from stdin.",
  },
  {
    id: "codex-cli",
    label: "Codex CLI",
    description: "codex exec in workspace-write sandbox, reads the prompt from stdin.",
  },
  {
    id: "echo",
    label: "Echo",
    description: "cat — echoes stdin back to stdout. Useful for testing the pipeline.",
  },
  {
    id: "custom",
    label: "Custom",
    description: "Type your own argv, one argument per line.",
  },
];

/** Default timeout (seconds) suggested when a preset is first selected. */
export const DEFAULT_TIMEOUT_S: Record<PresetId, number> = {
  "claude-code": 900,
  "codex-cli": 900,
  echo: 10,
  custom: 60,
};

export interface BuildAgentSpecParams {
  name: string;
  model?: string;
  maxTurns?: number;
  timeoutS: number;
  customArgvLines?: string;
  customInputMode?: AgentSpecInput["input_mode"];
  customOutputMode?: AgentSpecInput["output_mode"];
  env: Record<string, string>;
  requiredSecrets: string[];
}

/**
 * Builds the argv-only AgentSpec for a preset. Never shell-splits anything:
 * the "custom" preset takes each textarea line verbatim as one argv entry.
 */
export function buildAgentSpec(preset: PresetId, params: BuildAgentSpecParams): AgentSpecInput {
  const { name, model, timeoutS, env, requiredSecrets } = params;

  if (preset === "claude-code") {
    const command = ["claude", "-p", "--permission-mode", "acceptEdits", "--max-turns", String(params.maxTurns ?? 10)];
    if (model) command.push("--model", model);
    return {
      name,
      command,
      input_mode: "stdin",
      output_mode: "stdout",
      timeout_s: timeoutS,
      env,
      required_secrets: requiredSecrets,
    };
  }

  if (preset === "codex-cli") {
    const command = ["codex", "exec", "--skip-git-repo-check", "--sandbox", "workspace-write", "--ask-for-approval", "never"];
    if (model) command.push("--model", model);
    command.push("-o", "{output_file}", "-");
    return {
      name,
      command,
      input_mode: "stdin",
      output_mode: "file",
      timeout_s: timeoutS,
      env,
      required_secrets: requiredSecrets,
    };
  }

  if (preset === "echo") {
    return {
      name,
      command: ["cat"],
      input_mode: "stdin",
      output_mode: "stdout",
      timeout_s: timeoutS,
      env,
      required_secrets: requiredSecrets,
    };
  }

  // custom: each non-empty line is exactly one argv entry, no shell splitting.
  const command = (params.customArgvLines ?? "")
    .split("\n")
    .map((line) => line.replace(/\r$/, ""))
    .filter((line) => line.trim() !== "");

  return {
    name,
    command,
    input_mode: params.customInputMode ?? "stdin",
    output_mode: params.customOutputMode ?? "stdout",
    timeout_s: timeoutS,
    env,
    required_secrets: requiredSecrets,
  };
}

/**
 * Lowercases, collapses any run of characters outside SAFE_ID_RE's allowed
 * set into a single "-", and trims leading/trailing "-". Returns "" if the
 * result is empty or made only of dots (SAFE_ID_RE rejects dot-only ids).
 */
export function slugifyId(name: string): string {
  const lowered = name.toLowerCase();
  const collapsed = lowered.replace(/[^a-z0-9_.:-]+/g, "-");
  const trimmed = collapsed.replace(/^-+|-+$/g, "");
  if (trimmed === "" || /^\.+$/.test(trimmed)) return "";
  return trimmed;
}

export interface ParseEnvResult {
  env: Record<string, string>;
  errors: string[];
}

const ENV_KEY_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

/**
 * Parses `KEY=VALUE` lines (one per line, split at the first "="). Blank
 * lines are ignored. Lines missing "=" or with an invalid KEY are reported
 * in `errors` and excluded from `env`.
 */
export function parseEnvLines(text: string): ParseEnvResult {
  const env: Record<string, string> = {};
  const errors: string[] = [];

  for (const rawLine of text.split("\n")) {
    const line = rawLine.replace(/\r$/, "");
    if (line.trim() === "") continue;

    const idx = line.indexOf("=");
    if (idx === -1) {
      errors.push(`missing "=" in: ${line}`);
      continue;
    }

    const key = line.slice(0, idx).trim();
    const value = line.slice(idx + 1);
    if (!ENV_KEY_RE.test(key)) {
      errors.push(`invalid env key: ${key || "(empty)"}`);
      continue;
    }
    env[key] = value;
  }

  return { env, errors };
}

export interface DetectedPreset {
  preset: PresetId;
  model?: string;
  maxTurns?: number;
}

function arraysEqual(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

const CLAUDE_CODE_PREFIX = ["claude", "-p", "--permission-mode", "acceptEdits", "--max-turns"];
const CODEX_CLI_PREFIX = [
  "codex",
  "exec",
  "--skip-git-repo-check",
  "--sandbox",
  "workspace-write",
  "--ask-for-approval",
  "never",
];
const CODEX_CLI_SUFFIX = ["-o", "{output_file}", "-"];

/**
 * Infers which preset produced an existing agent command, for the edit
 * flow. Round-6 review (2026-09-12): a preset must only be detected when the
 * argv matches that preset's *exact* shape end to end (only the trailing
 * `--model <m>` pair may vary) — matching on argv[0] alone previously let a
 * hand-edited custom command starting with "claude" or "codex" get silently
 * rewritten to the preset's canonical shape on save. Anything that does not
 * match one of the exact shapes below falls back to "custom", which
 * preserves the original argv verbatim.
 */
export function detectPreset(agent: { command: string[] }): DetectedPreset {
  const command = agent.command;

  if (arraysEqual(command.slice(0, CLAUDE_CODE_PREFIX.length), CLAUDE_CODE_PREFIX)) {
    const maxTurnsRaw = command[CLAUDE_CODE_PREFIX.length];
    const parsedMaxTurns = maxTurnsRaw !== undefined ? Number(maxTurnsRaw) : NaN;
    if (maxTurnsRaw !== undefined && maxTurnsRaw !== "" && !Number.isNaN(parsedMaxTurns)) {
      const rest = command.slice(CLAUDE_CODE_PREFIX.length + 1);
      if (rest.length === 0) {
        return { preset: "claude-code", maxTurns: parsedMaxTurns };
      }
      if (rest.length === 2 && rest[0] === "--model") {
        return { preset: "claude-code", maxTurns: parsedMaxTurns, model: rest[1] };
      }
    }
  }

  if (arraysEqual(command.slice(0, CODEX_CLI_PREFIX.length), CODEX_CLI_PREFIX)) {
    const rest = command.slice(CODEX_CLI_PREFIX.length);
    if (arraysEqual(rest, CODEX_CLI_SUFFIX)) {
      return { preset: "codex-cli" };
    }
    if (rest.length === 5 && rest[0] === "--model" && arraysEqual(rest.slice(2), CODEX_CLI_SUFFIX)) {
      return { preset: "codex-cli", model: rest[1] };
    }
  }

  if (arraysEqual(command, ["cat"])) {
    return { preset: "echo" };
  }

  return { preset: "custom" };
}

/** Quotes an argv entry for display only if it contains whitespace. */
export function quoteArgIfNeeded(arg: string): string {
  return /\s/.test(arg) ? `"${arg}"` : arg;
}

/** Read-only preview string for a generated command, e.g. for a form's "Command" field. */
export function formatCommandPreview(command: string[]): string {
  return command.map(quoteArgIfNeeded).join(" ");
}

/** Truncated argv summary for list rows. */
export function formatArgvSummary(command: string[], maxLen = 72): string {
  const joined = formatCommandPreview(command);
  return joined.length > maxLen ? joined.slice(0, maxLen - 1) + "…" : joined;
}
