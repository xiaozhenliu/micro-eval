import { NextResponse } from "next/server";
import { isServerMode } from "@/lib/server-mode";
import { resolveWritableWorkspace } from "@/lib/workspace-write";
import { validateWriteRequest, sanitizeErrorDetail } from "@/lib/server-validation";
import { SAFE_ID_RE } from "@/lib/project-schema";
import { removeTask, ProjectApiError } from "@/lib/project-api";

interface RouteContext {
  params: Promise<{ id: string; taskId: string }>;
}

/** Delete tasks/<id>.yaml and remove it from eval.yaml's tasks: list (GRO-550). */
export async function DELETE(request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const validation = validateWriteRequest(request);
  if (validation instanceof NextResponse) return validation;
  const { member } = validation;

  const { id, taskId } = await context.params;
  if (!SAFE_ID_RE.test(taskId)) {
    return NextResponse.json({ error: "invalid task id" }, { status: 400 });
  }

  const writable = resolveWritableWorkspace(id);
  if ("error" in writable) return NextResponse.json({ error: writable.error }, { status: writable.status });
  const { wsPath } = writable;

  try {
    const draft = removeTask(wsPath, taskId, member);
    return NextResponse.json(draft);
  } catch (err) {
    if (err instanceof ProjectApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    const detail = sanitizeErrorDetail(err instanceof Error ? err.message : String(err));
    return NextResponse.json({ error: "failed to remove task", detail }, { status: 502 });
  }
}
