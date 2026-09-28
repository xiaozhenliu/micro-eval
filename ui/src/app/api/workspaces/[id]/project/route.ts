import { NextResponse } from "next/server";
import { isServerMode } from "@/lib/server-mode";
import { resolveWorkspacePath } from "@/lib/workspace-api";
import { sanitizeErrorDetail } from "@/lib/server-validation";
import { readProjectDraft, ProjectApiError } from "@/lib/project-api";

interface RouteContext {
  params: Promise<{ id: string }>;
}

/**
 * Read-only project draft: configurations, tasks, and any per-entry
 * validation errors, produced by `micro-eval config show` (GRO-549/GRO-550).
 */
export async function GET(_request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const { id } = await context.params;
  const wsPath = resolveWorkspacePath(id);
  if (!wsPath) return NextResponse.json({ error: "workspace not found" }, { status: 404 });

  try {
    const draft = readProjectDraft(wsPath);
    return NextResponse.json(draft);
  } catch (err) {
    if (err instanceof ProjectApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    const detail = sanitizeErrorDetail(err instanceof Error ? err.message : String(err));
    return NextResponse.json({ error: "failed to read project", detail }, { status: 502 });
  }
}
