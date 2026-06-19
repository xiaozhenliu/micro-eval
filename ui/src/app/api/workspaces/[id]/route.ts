import { execFileSync } from "node:child_process";
import { NextResponse } from "next/server";
import { z } from "zod";
import { isServerMode, getServerDataRoot } from "@/lib/server-mode";
import { readWorkspaceMeta, resolveWorkspacePath } from "@/lib/workspace-api";
import { validateWriteRequest, uvBin, queryQueue } from "@/lib/server-validation";

interface RouteContext {
  params: Promise<{ id: string }>;
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

  const args = ["run", "micro-eval", "workspace", "update", id];
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
    const detail = err instanceof Error ? err.message : String(err);
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
      `result = db.has_pending_jobs(${JSON.stringify(id)})\nprint(json.dumps(result))`,
    ) as boolean;
    if (hasPending) {
      return NextResponse.json(
        { error: "workspace has pending jobs; cancel them before deleting" },
        { status: 409 },
      );
    }
  } catch {
    // queue.db may not exist yet — treat as no pending jobs
  }

  const wsPath = resolveWorkspacePath(id);
  if (!wsPath) return NextResponse.json({ error: "workspace not found" }, { status: 404 });

  const args = ["run", "micro-eval", "workspace", "delete", id, "--force"];
  try {
    execFileSync(uvBin(), args, {
      encoding: "utf-8",
      cwd: getServerDataRoot(),
      timeout: 30_000,
    });
    return NextResponse.json({ deleted: true, workspace_id: id });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: "workspace deletion failed", detail }, { status: 502 });
  }
}
