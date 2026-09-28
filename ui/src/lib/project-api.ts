/**
 * Server-only bridge to `micro-eval config` (GRO-550). Every call is
 * argv-only: fixed flags, the resolved workspace path (already validated by
 * resolveWorkspacePath), and ids that already passed SAFE_ID_RE. User JSON
 * payloads are never interpolated into argv — they go through stdin only.
 */
import { execFileSync } from "node:child_process";
import { uvBin, sanitizeErrorDetail } from "./server-validation";
import {
  ProjectDraftSchema,
  RawConfigSchema,
  SAFE_ID_RE,
  SetRawResultSchema,
  isSafeTaskPath,
  type ConfigurationInput,
  type ProjectDraft,
  type RawConfig,
  type TaskInput,
} from "./project-schema";

const EXEC_TIMEOUT_MS = 30_000;

/**
 * `status` mirrors the HTTP status the caller (a route handler) should
 * return: 400 for a CLI `kind: "validation"` error, 404 for `"not_found"`,
 * 502 for `"internal"` or any non-structured failure (F8/F10).
 */
export class ProjectApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function assertSafeId(id: string): void {
  if (!SAFE_ID_RE.test(id)) {
    throw new ProjectApiError("invalid id", 400);
  }
}

function assertSafeTaskPath(relPath: string): void {
  if (!isSafeTaskPath(relPath)) {
    throw new ProjectApiError("invalid task path", 400);
  }
}

function statusForKind(kind: unknown): number {
  if (kind === "validation") return 400;
  if (kind === "not_found") return 404;
  if (kind === "conflict") return 409;
  return 502;
}

/**
 * The CLI prints `{"error": "<message>", "kind": "validation"|"not_found"|"internal"}`
 * to stderr on failure. The error message is already path-free by contract.
 * `uv run` may prepend its own warnings (e.g. a stale-lockfile notice) as
 * extra lines before the CLI's JSON, so scan stderr line by line from the
 * end and use the last line that parses as an object with a string `error`
 * field (N9) rather than assuming the whole of stderr — or its first line —
 * is the JSON payload. When no line matches (e.g. a raw Python traceback
 * from an unexpected crash), never surface it — return a fixed,
 * exit-code-only message instead so nothing internal leaks (F8/F10).
 */
function extractCliError(stderr: string, exitCode: number | null): { message: string; status: number } {
  const lines = stderr.split("\n");
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const line = lines[i].trim();
    if (line === "") continue;
    let parsed: unknown;
    try {
      parsed = JSON.parse(line);
    } catch {
      continue;
    }
    if (parsed && typeof parsed === "object" && "error" in parsed) {
      const errorField = (parsed as { error: unknown }).error;
      if (typeof errorField === "string") {
        const kind = (parsed as { kind?: unknown }).kind;
        return { message: errorField, status: statusForKind(kind) };
      }
    }
  }
  return { message: `config command failed (exit ${exitCode ?? "unknown"})`, status: 502 };
}

/**
 * Runs `micro-eval config <args>` and returns the parsed JSON stdout,
 * untyped. Shared by `runConfigCommand` (which additionally validates the
 * result against ProjectDraftSchema) and the raw-config functions below
 * (whose stdout shape — `{content, redacted}` or `{saved: true}` — is not a
 * ProjectDraft).
 */
function execConfigCommand(args: string[], input?: string): unknown {
  let stdout: string;
  try {
    stdout = execFileSync(uvBin(), ["run", "micro-eval", "config", ...args], {
      encoding: "utf-8",
      timeout: EXEC_TIMEOUT_MS,
      // A 1 MiB eval.yaml (the Advanced limit) plus JSON framing must fit;
      // Node's default maxBuffer is exactly 1 MiB (round-12 review).
      maxBuffer: 8 * 1024 * 1024,
      ...(input !== undefined ? { input } : {}),
    });
  } catch (err) {
    const errObj = err as { stderr?: string | Buffer; status?: number | null };
    const stderr = errObj.stderr !== undefined ? String(errObj.stderr) : err instanceof Error ? err.message : String(err);
    const { message, status } = extractCliError(stderr, errObj.status ?? null);
    // Defense in depth: strip any absolute path that slipped through even
    // though the message is already expected to be path-free.
    throw new ProjectApiError(sanitizeErrorDetail(message), status);
  }

  try {
    return JSON.parse(stdout);
  } catch {
    throw new ProjectApiError("config command returned invalid JSON", 502);
  }
}

function runConfigCommand(args: string[], input?: string): ProjectDraft {
  return ProjectDraftSchema.parse(execConfigCommand(args, input));
}

export function readProjectDraft(wsPath: string): ProjectDraft {
  return runConfigCommand(["show", "--project", wsPath]);
}

/**
 * Reads eval.yaml through the hardened CLI layer instead of the filesystem
 * directly (N1): the CLI replaces declared secret values with
 * `[REDACTED:<NAME>]` before the text ever reaches the UI process, so the
 * Advanced tab's raw editor can no longer leak `agent.env` secrets. Missing
 * eval.yaml comes back as `{content: "", redacted: false}`.
 */
export function readRawConfig(wsPath: string): RawConfig {
  return RawConfigSchema.parse(execConfigCommand(["show-raw", "--project", wsPath]));
}

/**
 * Writes eval.yaml verbatim through the hardened CLI layer (N1): the CLI
 * validates the YAML (size, ConfigurationSpec/TaskSpec shape, safe relative
 * paths, no bare secret values in `agent.env`, and no leftover
 * `[REDACTED` placeholder) before writing it through its fd-based writer.
 * Throws ProjectApiError on any validation failure; returns nothing on
 * success since `set-raw` prints `{"saved": true}`, not a draft.
 */
export function writeRawConfig(wsPath: string, content: string, member: string): void {
  SetRawResultSchema.parse(
    execConfigCommand(["set-raw", "--project", wsPath, "--member", member, "--active-workspace-only"], JSON.stringify({ content })),
  );
}

export function setConfiguration(wsPath: string, payload: ConfigurationInput, member: string): ProjectDraft {
  return runConfigCommand(["set-configuration", "--project", wsPath, "--member", member, "--active-workspace-only"], JSON.stringify(payload));
}

export function removeConfiguration(wsPath: string, id: string, member: string): ProjectDraft {
  assertSafeId(id);
  return runConfigCommand(["remove-configuration", "--project", wsPath, "--id", id, "--member", member, "--active-workspace-only"]);
}

export function setTask(wsPath: string, payload: TaskInput, member: string): ProjectDraft {
  return runConfigCommand(["set-task", "--project", wsPath, "--member", member, "--active-workspace-only"], JSON.stringify(payload));
}

export function removeTask(wsPath: string, id: string, member: string): ProjectDraft {
  assertSafeId(id);
  return runConfigCommand(["remove-task", "--project", wsPath, "--id", id, "--member", member, "--active-workspace-only"]);
}

/** Delete a task entry by its file path, for entries that failed to parse (F6). */
export function removeTaskByPath(wsPath: string, relPath: string, member: string): ProjectDraft {
  assertSafeTaskPath(relPath);
  return runConfigCommand(["remove-task", "--project", wsPath, "--path", relPath, "--member", member, "--active-workspace-only"]);
}
