import { NextResponse } from "next/server";
import { isServerMode } from "@/lib/server-mode";
import { resolveWritableWorkspace } from "@/lib/workspace-write";
import { validateWriteRequest, sanitizeErrorDetail } from "@/lib/server-validation";
import { TaskInputSchema, isSafeTaskPath } from "@/lib/project-schema";
import { setTask, removeTaskByPath, ProjectApiError } from "@/lib/project-api";

interface RouteContext {
  params: Promise<{ id: string }>;
}

/**
 * Upsert one task as `tasks/<id>.yaml` and register it in eval.yaml's
 * `tasks:` list (GRO-550). The validated JSON body is sent to the CLI over
 * stdin only; nothing user-authored ever enters argv.
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

  const parsed = TaskInputSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "invalid task", detail: parsed.error.message }, { status: 400 });
  }

  try {
    const draft = setTask(wsPath, parsed.data, member);
    return NextResponse.json(draft);
  } catch (err) {
    if (err instanceof ProjectApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    const detail = sanitizeErrorDetail(err instanceof Error ? err.message : String(err));
    return NextResponse.json({ error: "failed to save task", detail }, { status: 502 });
  }
}

/**
 * Delete a task entry by its file path (`?path=tasks/<id>.yaml`), for
 * entries whose task body failed to parse and therefore have no usable id
 * (F6). Id-based deletes keep using DELETE /tasks/[taskId].
 */
export async function DELETE(request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const validation = validateWriteRequest(request);
  if (validation instanceof NextResponse) return validation;
  const { member } = validation;

  const { id } = await context.params;
  const writable = resolveWritableWorkspace(id);
  if ("error" in writable) return NextResponse.json({ error: writable.error }, { status: writable.status });
  const { wsPath } = writable;

  const relPath = new URL(request.url).searchParams.get("path");
  if (!relPath || !isSafeTaskPath(relPath)) {
    return NextResponse.json({ error: "invalid task path" }, { status: 400 });
  }

  try {
    const draft = removeTaskByPath(wsPath, relPath, member);
    return NextResponse.json(draft);
  } catch (err) {
    if (err instanceof ProjectApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    const detail = sanitizeErrorDetail(err instanceof Error ? err.message : String(err));
    return NextResponse.json({ error: "failed to remove task", detail }, { status: 502 });
  }
}
