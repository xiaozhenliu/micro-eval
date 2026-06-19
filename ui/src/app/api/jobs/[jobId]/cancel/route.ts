import { NextResponse } from "next/server";
import { isServerMode } from "@/lib/server-mode";
import { validateWriteRequest, queryQueue, safeJobId } from "@/lib/server-validation";

interface RouteContext {
  params: Promise<{ jobId: string }>;
}

export async function POST(request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const validation = validateWriteRequest(request);
  if (validation instanceof NextResponse) return validation;
  const { member } = validation;

  const { jobId } = await context.params;
  const safe = safeJobId(jobId);
  if (!safe) return NextResponse.json({ error: "invalid job id" }, { status: 400 });

  try {
    const result = queryQueue(
      `result = db.request_cancel(${JSON.stringify(safe)}, ${JSON.stringify(member)})\nprint(json.dumps(result))`,
    ) as Record<string, unknown> | null;

    if (result === null) {
      return NextResponse.json({ error: "job not found" }, { status: 404 });
    }
    if (result.error === "job_already_terminated") {
      return NextResponse.json(result, { status: 409 });
    }
    return NextResponse.json(result);
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: "cancel failed", detail }, { status: 502 });
  }
}
