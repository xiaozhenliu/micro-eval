import { NextResponse } from "next/server";
import { isServerMode } from "@/lib/server-mode";
import { resolveWritableWorkspace } from "@/lib/workspace-write";
import { validateWriteRequest, sanitizeErrorDetail } from "@/lib/server-validation";
import { SAFE_ID_RE } from "@/lib/project-schema";
import { removeConfiguration, ProjectApiError } from "@/lib/project-api";

interface RouteContext {
  params: Promise<{ id: string; configId: string }>;
}

/** Remove a configuration by id (GRO-550). */
export async function DELETE(request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const validation = validateWriteRequest(request);
  if (validation instanceof NextResponse) return validation;
  const { member } = validation;

  const { id, configId } = await context.params;
  if (!SAFE_ID_RE.test(configId)) {
    return NextResponse.json({ error: "invalid configuration id" }, { status: 400 });
  }

  const writable = resolveWritableWorkspace(id);
  if ("error" in writable) return NextResponse.json({ error: writable.error }, { status: writable.status });
  const { wsPath } = writable;

  try {
    const draft = removeConfiguration(wsPath, configId, member);
    return NextResponse.json(draft);
  } catch (err) {
    if (err instanceof ProjectApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    const detail = sanitizeErrorDetail(err instanceof Error ? err.message : String(err));
    return NextResponse.json({ error: "failed to remove configuration", detail }, { status: 502 });
  }
}
