import { NextResponse } from "next/server";
import { isServerMode } from "@/lib/server-mode";
import { resolveWorkspacePath } from "@/lib/workspace-api";
import { resolveWritableWorkspace } from "@/lib/workspace-write";
import { validateWriteRequest, sanitizeErrorDetail } from "@/lib/server-validation";
import { readRawConfig, writeRawConfig, ProjectApiError } from "@/lib/project-api";

interface RouteContext {
  params: Promise<{ id: string }>;
}

// Maximum allowed eval.yaml size (1 MiB, same as the CLI)
const MAX_YAML_BYTES = 1024 * 1024;

/**
 * Reads eval.yaml through the hardened `micro-eval config show-raw` layer
 * (N1) instead of the filesystem directly: declared secret values are
 * already replaced with `[REDACTED:<NAME>]` by the CLI, so this route can
 * never leak `agent.env` secrets even though it serves the Advanced tab's
 * raw-YAML editor.
 */
export async function GET(_request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const { id } = await context.params;
  const wsPath = resolveWorkspacePath(id);
  if (!wsPath) return NextResponse.json({ error: "workspace not found" }, { status: 404 });

  try {
    const raw = readRawConfig(wsPath);
    return NextResponse.json(raw);
  } catch (err) {
    if (err instanceof ProjectApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    const detail = sanitizeErrorDetail(err instanceof Error ? err.message : String(err));
    return NextResponse.json({ error: "failed to read config", detail }, { status: 502 });
  }
}

/**
 * Writes eval.yaml through `micro-eval config set-raw` (N1) instead of a raw
 * filesystem write: the CLI validates size, ConfigurationSpec/TaskSpec
 * shape, safe relative paths, absence of bare `agent.env` secrets, and
 * absence of a leftover `[REDACTED` placeholder before writing anything.
 * The 1 MiB check here is a cheap early rejection; the CLI enforces the
 * same limit again on its side.
 */
export async function PUT(request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const validation = validateWriteRequest(request);
  if (validation instanceof NextResponse) return validation;
  const { member } = validation;

  const { id } = await context.params;
  const writable = resolveWritableWorkspace(id);
  if ("error" in writable) return NextResponse.json({ error: writable.error }, { status: writable.status });
  const { wsPath } = writable;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  // `null` and non-objects parse as valid JSON; guard before property access.
  if (body === null || typeof body !== "object" || typeof (body as { content?: unknown }).content !== "string") {
    return NextResponse.json({ error: "body.content must be a string" }, { status: 400 });
  }

  const yamlContent: string = (body as { content: string }).content;
  if (Buffer.byteLength(yamlContent, "utf-8") > MAX_YAML_BYTES) {
    return NextResponse.json({ error: "eval.yaml too large (max 1 MiB)" }, { status: 413 });
  }

  try {
    writeRawConfig(wsPath, yamlContent, member);
    return NextResponse.json({ saved: true });
  } catch (err) {
    if (err instanceof ProjectApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    const detail = sanitizeErrorDetail(err instanceof Error ? err.message : String(err));
    return NextResponse.json({ error: "failed to save config", detail }, { status: 502 });
  }
}
