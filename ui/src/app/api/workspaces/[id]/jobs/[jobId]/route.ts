import { NextResponse } from "next/server";
import { isServerMode } from "@/lib/server-mode";
import { readWorkspaceMeta } from "@/lib/workspace-api";
import { queryQueue, safeJobId, sanitizeErrorDetail, stripPlanJson } from "@/lib/server-validation";

interface RouteContext {
  params: Promise<{ id: string; jobId: string }>;
}

export async function GET(_request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const { id, jobId } = await context.params;
  if (!readWorkspaceMeta(id)) {
    return NextResponse.json({ error: "workspace not found" }, { status: 404 });
  }
  const safe = safeJobId(jobId);
  if (!safe) return NextResponse.json({ error: "invalid job id" }, { status: 400 });

  try {
    const job = queryQueue(
      `result = db.get_job(os.environ['_JOB_ID'])\nprint(json.dumps(result))`,
      undefined,
      { _JOB_ID: safe },
    ) as { workspace_id?: string } | null;
    if (job === null || job.workspace_id !== id) {
      return NextResponse.json({ error: "job not found" }, { status: 404 });
    }
    // A stored RunPlan can contain agent.env; it must not leave the server.
    return NextResponse.json(stripPlanJson(job));
  } catch (err) {
    const detail = sanitizeErrorDetail(err instanceof Error ? err.message : String(err));
    return NextResponse.json({ error: "queue read failed", detail }, { status: 502 });
  }
}
