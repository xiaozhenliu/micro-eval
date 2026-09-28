import { execFileSync } from "node:child_process";
import { NextResponse } from "next/server";
import { getServerDataRoot } from "./server-mode";

const MEMBER_RE = /^[a-zA-Z0-9._-]{1,64}$/;

/**
 * Validates write requests: content-type and X-Micro-Eval-Member header.
 * Returns { member } on success, or a NextResponse error on failure.
 */
export function validateWriteRequest(
  request: Request,
): { member: string } | NextResponse {
  const contentType = request.headers.get("content-type");
  const mediaType = (contentType ?? "").split(";")[0].trim().toLowerCase();
  if (mediaType !== "application/json") {
    return NextResponse.json(
      { error: "content type must be application/json" },
      { status: 400 },
    );
  }
  const member = request.headers.get("x-micro-eval-member");
  if (!member || !MEMBER_RE.test(member)) {
    return NextResponse.json(
      { error: "valid X-Micro-Eval-Member header required" },
      { status: 400 },
    );
  }
  return { member };
}

/**
 * Executes a Python snippet via `uv run python -c` with the queue.db path
 * injected through the MICRO_EVAL_DATA_ROOT env var (never via string interpolation).
 * The snippet must print a single JSON value to stdout.
 * Pass values via `extraEnv` instead of string-interpolating into the snippet.
 */
export function queryQueue(
  pythonSnippet: string,
  input?: string,
  extraEnv?: Record<string, string>,
): unknown {
  const uvBin = process.env.MICRO_EVAL_UV_PATH || "uv";
  const dataRoot = getServerDataRoot();
  const wrapper = `
import json, sys, os
sys.path.insert(0, '.')
from micro_eval.server.queue import QueueDB
_db_path = os.environ['_QUEUE_DB_PATH']
db = QueueDB(_db_path)
try:
${pythonSnippet
  .split("\n")
  .map((l) => "    " + l)
  .join("\n")}
finally:
    db.close()
`;
  const stdout = execFileSync(uvBin, ["run", "python", "-c", wrapper], {
    encoding: "utf-8",
    timeout: 10_000,
    maxBuffer: 16 * 1024 * 1024,
    env: {
      ...process.env,
      _QUEUE_DB_PATH: dataRoot + "/queue.db",
      ...extraEnv,
    },
    ...(input !== undefined ? { input } : {}),
  });
  return JSON.parse(stdout.trim());
}

/**
 * Returns the `uv` binary path from env or falls back to "uv".
 */
export function uvBin(): string {
  return process.env.MICRO_EVAL_UV_PATH || "uv";
}

/**
 * Safe path-segment ID regex: alphanumerics + dot/hyphen/underscore/colon,
 * 1+ chars, excluding pure-dot names (`.`, `..`). Used for runId, cellId, etc.
 * Prevents path traversal when the ID is used in path.join().
 */
export const SAFE_SEGMENT_RE = /^(?!\.+$)[A-Za-z0-9_.:-]+$/;

/**
 * Sanitises a job_id: only hex-safe chars and hyphens (job-YYYYMMDDTHHMMSSZ-xxxxxxxx).
 */
export function safeJobId(id: string): string | null {
  return /^job-\d{8}T\d{6}Z-[a-f0-9]{8}$/.test(id) ? id : null;
}

/**
 * Allowed template_id charset: alphanumerics plus dot/hyphen/underscore, 1-64
 * chars, and never a pure-dot name — the negative lookahead rejects `.`/`..`
 * so a caller-supplied id cannot escape the templates root (H1). JS `$` (no `m`
 * flag) anchors the true end of input, so a trailing newline cannot slip through.
 */
export const TEMPLATE_ID_RE = /^(?!\.+$)[a-zA-Z0-9._-]{1,64}$/;

/**
 * Sanitises a template_id: alphanumeric, dot, hyphen, underscore, 1-64 chars,
 * excluding pure-dot names. Returns null if invalid.
 */
export function safeTemplateId(id: string): string | null {
  return TEMPLATE_ID_RE.test(id) ? id : null;
}

/**
 * Strip absolute paths and truncate error detail before returning to client.
 * Prevents leaking server directory structure in error responses (GRO-190).
 */
export function sanitizeErrorDetail(detail: string): string {
  // Strip absolute paths (Unix and Windows)
  const stripped = detail.replace(/(?:\/[\w./-]+|[A-Z]:\\[\w.\\-]+)/g, "<path>");
  // Keep last 200 chars to avoid leaking long stack traces
  if (stripped.length > 200) return "..." + stripped.slice(-200);
  return stripped;
}

/**
 * Remove the stored RunPlan from a queue job row before it leaves the server.
 * `plan_json` embeds every configuration verbatim, including `agent.env`,
 * and no UI surface needs it (round-4 review, 2026-09-12).
 */
export function stripPlanJson<T>(row: T): Omit<T, "plan_json"> {
  if (row === null || typeof row !== "object") return row as Omit<T, "plan_json">;
  const { plan_json: _omitted, ...rest } = row as T & { plan_json?: unknown };
  void _omitted;
  return rest;
}

const SECRET_ENV_PREFIX = "MICRO_EVAL_SECRET_";

/**
 * Mask declared `MICRO_EVAL_SECRET_*` values inside a string: an exact match
 * of the whole string is masked first (round-6 review, 2026-09-12: any
 * declared secret value is masked as a substring regardless of length — a
 * short secret pasted inside a longer string, e.g. a Bearer header, must not
 * survive redaction just because it is short).
 */
export function redactDeclaredSecrets(text: string, env: NodeJS.ProcessEnv = process.env): string {
  const secrets = Object.entries(env).filter(
    (entry): entry is [string, string] => entry[0].startsWith(SECRET_ENV_PREFIX) && typeof entry[1] === "string" && entry[1].length > 0,
  );
  for (const [name, value] of secrets) {
    if (text === value) return `[REDACTED:${name}]`;
  }
  let redacted = text;
  for (const [name, value] of secrets) {
    const placeholder = `[REDACTED:${name}]`;
    redacted = redacted.split(value).join(placeholder);
  }
  return redacted;
}

const SOURCE_PREFLIGHT_DETAIL_RE =
  /^(task [A-Za-z0-9_.:-]+: (?:workspace source not found|workspace source is not a git repo|git ref cannot be resolved for workspace source): )(\.|[^/\\\r\n][^\\\r\n]*)$/;

/** Preserve validated relative source paths without relaxing generic error masking. */
export function sanitizePlanBuildDetail(detail: string, env: NodeJS.ProcessEnv = process.env): string {
  const redacted = redactDeclaredSecrets(detail, env);
  const match = SOURCE_PREFLIGHT_DETAIL_RE.exec(redacted);
  if (!match) return sanitizeErrorDetail(redacted);
  const [, prefix, source] = match;
  if (source !== "." && source.split("/").some((part) => !part || part === "." || part === "..")) {
    return sanitizeErrorDetail(redacted);
  }
  const maxSourceLength = 200 - prefix.length;
  if (maxSourceLength < 4) return sanitizeErrorDetail(redacted);
  return source.length > maxSourceLength
    ? `${prefix}${source.slice(0, maxSourceLength - 3)}...`
    : redacted;
}

/**
 * The `micro-eval workspace enqueue` CLI prints one JSON object on stderr
 * when it refuses (`{"error": "<kind>", ...}`). Return the last JSON line so
 * a warning printed before it does not hide the refusal.
 */
export function parseCliRefusal(err: unknown): Record<string, unknown> | null {
  const failure = err as { stderr?: string | Buffer };
  const text = failure.stderr !== undefined ? String(failure.stderr) : "";
  const lines = text.split("\n").filter((line) => line.trim().length > 0);
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    try {
      const parsed = JSON.parse(lines[index]) as unknown;
      if (parsed && typeof parsed === "object" && typeof (parsed as { error?: unknown }).error === "string") {
        return parsed as Record<string, unknown>;
      }
    } catch {
      // not a JSON line
    }
  }
  return null;
}
