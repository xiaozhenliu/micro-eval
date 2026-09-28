import { execFileSync } from "node:child_process";
import { NextResponse } from "next/server";
import { z } from "zod";
import { isServerMode, getServerDataRoot } from "@/lib/server-mode";
import { readWorkspaceMeta, resolveWorkspacePath } from "@/lib/workspace-api";
import { validateWriteRequest, uvBin, queryQueue, sanitizeErrorDetail } from "@/lib/server-validation";

interface RouteContext {
  params: Promise<{ id: string }>;
}

/** True only for the "queue.db was never created" failure of `queryQueue`. */
function isMissingQueueDb(err: unknown): boolean {
  const msg = err instanceof Error ? err.message : String(err);
  return msg.includes("unable to open") || msg.includes("no such file");
}

/**
 * True when the `workspace update|delete` CLI exited because the workspace
 * still has queued or running jobs (checked under the workspace lock).
 */
function cliRefusedForPendingJobs(err: unknown): boolean {
  const failure = err as { status?: number | null; stderr?: string | Buffer };
  const stderr = failure.stderr !== undefined ? String(failure.stderr) : "";
  return failure.status === 1 && stderr.includes("pending");
}

const PatchWorkspaceSchema = z.object({
  name: z.string().min(1).max(120).optional(),
  description: z.string().max(500).optional(),
  status: z.enum(["active", "archived"]).optional(),
});

export async function GET(_request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });
  const { id } = await context.params;
  const meta = readWorkspaceMeta(id);
  if (!meta) return NextResponse.json({ error: "workspace not found" }, { status: 404 });
  return NextResponse.json(meta);
}

export async function PATCH(request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const validation = validateWriteRequest(request);
  if (validation instanceof NextResponse) return validation;

  const { id } = await context.params;
  const meta = readWorkspaceMeta(id);
  if (!meta) return NextResponse.json({ error: "workspace not found" }, { status: 404 });

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  let input: z.infer<typeof PatchWorkspaceSchema>;
  try {
    input = PatchWorkspaceSchema.parse(body);
  } catch (err) {
    return NextResponse.json({ error: "invalid request body", detail: String(err) }, { status: 400 });
  }

  // Workspace/queue interlock: never archive a workspace whose jobs are still
  // queued or running (round-5 review, 2026-09-12). Mirrors the delete guard.
  if (input.status === "archived") {
    try {
      const hasPending = queryQueue(
        `result = db.has_pending_jobs(os.environ['_WS_ID'])\nprint(json.dumps(result))`,
        undefined,
        { _WS_ID: id },
      ) as boolean;
      if (hasPending) {
        return NextResponse.json(
          { error: "workspace has pending jobs; cancel them before archiving" },
          { status: 409 },
        );
      }
    } catch (err) {
      // queue.db not existing yet is the one expected failure mode (no jobs
      // were ever enqueued) and is safe to treat as "no pending jobs", same
      // as the queue dashboard route. Any other failure (e.g. a locked or
      // corrupt queue.db) must fail closed: we cannot prove there are no
      // pending jobs, so refuse the archive rather than silently proceeding
      // (round-6 review, 2026-09-12).
      if (!isMissingQueueDb(err)) {
        return NextResponse.json({ error: "queue check failed" }, { status: 502 });
      }
    }
  }

  // Explicit --data-root: the CLI default ignores cwd and env (GRO-555).
  const args = ["run", "micro-eval", "workspace", "update", id, "--data-root", getServerDataRoot()];
  if (input.name !== undefined) args.push("--name", input.name);
  if (input.description !== undefined) args.push("--description", input.description);
  if (input.status !== undefined) args.push("--status", input.status);

  try {
    const stdout = execFileSync(uvBin(), args, {
      encoding: "utf-8",
      cwd: getServerDataRoot(),
      timeout: 30_000,
    });
    return NextResponse.json(JSON.parse(stdout));
  } catch (err) {
    // The CLI re-checks pending jobs under the workspace lock; a job admitted
    // between our pre-check and the update surfaces here (round-6 review).
    if (cliRefusedForPendingJobs(err)) {
      return NextResponse.json(
        { error: "workspace has pending jobs; cancel them before archiving" },
        { status: 409 },
      );
    }
    const detail = sanitizeErrorDetail(err instanceof Error ? err.message : String(err));
    return NextResponse.json({ error: "workspace update failed", detail }, { status: 502 });
  }
}

export async function DELETE(request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const validation = validateWriteRequest(request);
  if (validation instanceof NextResponse) return validation;

  const { id } = await context.params;
  const meta = readWorkspaceMeta(id);
  if (!meta) return NextResponse.json({ error: "workspace not found" }, { status: 404 });

  // Check no pending jobs before deletion
  try {
    const hasPending = queryQueue(
      `result = db.has_pending_jobs(os.environ['_WS_ID'])\nprint(json.dumps(result))`,
      undefined,
      { _WS_ID: id },
    ) as boolean;
    if (hasPending) {
      return NextResponse.json(
        { error: "workspace has pending jobs; cancel them before deleting" },
        { status: 409 },
      );
    }
  } catch (err) {
    // Same fail-closed rule as the archive path above: only a missing
    // queue.db means "no jobs"; any other failure refuses the delete.
    if (!isMissingQueueDb(err)) {
      return NextResponse.json({ error: "queue check failed" }, { status: 502 });
    }
  }

  const wsPath = resolveWorkspacePath(id);
  if (!wsPath) return NextResponse.json({ error: "workspace not found" }, { status: 404 });

  const args = ["run", "micro-eval", "workspace", "delete", id, "--force", "--data-root", getServerDataRoot()];
  try {
    execFileSync(uvBin(), args, {
      encoding: "utf-8",
      cwd: getServerDataRoot(),
      timeout: 30_000,
    });
    return NextResponse.json({ deleted: true, workspace_id: id });
  } catch (err) {
    if (cliRefusedForPendingJobs(err)) {
      return NextResponse.json(
        { error: "workspace has pending jobs; cancel them before deleting" },
        { status: 409 },
      );
    }
    const detail = sanitizeErrorDetail(err instanceof Error ? err.message : String(err));
    return NextResponse.json({ error: "workspace deletion failed", detail }, { status: 502 });
  }
}
