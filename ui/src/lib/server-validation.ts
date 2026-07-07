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
 */
export function queryQueue(pythonSnippet: string, input?: string): unknown {
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
    env: {
      ...process.env,
      _QUEUE_DB_PATH: dataRoot + "/queue.db",
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
