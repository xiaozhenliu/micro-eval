import { NextResponse } from "next/server";
import { isServerMode } from "@/lib/server-mode";
import { queryQueue, safeJobId, sanitizeErrorDetail } from "@/lib/server-validation";

interface RouteContext {
  params: Promise<{ jobId: string }>;
}

export async function GET(_request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const { jobId } = await context.params;
  const safe = safeJobId(jobId);
  if (!safe) return NextResponse.json({ error: "invalid job id" }, { status: 400 });

  try {
    const job = queryQueue(
      `result = db.get_job(os.environ['_JOB_ID'])\nprint(json.dumps(result))`,
      undefined,
      { _JOB_ID: safe },
    );
    if (job === null) return NextResponse.json({ error: "job not found" }, { status: 404 });
    return NextResponse.json(job);
  } catch (err) {
    const detail = sanitizeErrorDetail(err instanceof Error ? err.message : String(err));
    return NextResponse.json({ error: "queue read failed", detail }, { status: 502 });
  }
}
