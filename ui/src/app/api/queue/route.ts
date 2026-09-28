import { NextResponse } from "next/server";
import { isServerMode } from "@/lib/server-mode";
import { queryQueue, sanitizeErrorDetail, stripPlanJson } from "@/lib/server-validation";

interface DashboardRows {
  running?: unknown;
  queued?: unknown[];
  recent_completed?: unknown[];
}

export async function GET() {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  try {
    const dashboard = queryQueue(
      `result = db.get_queue_dashboard()\nprint(json.dumps(result))`,
    ) as DashboardRows;
    // Job rows carry the full RunPlan (including agent.env); the dashboard
    // never needs it and it must not leave the server.
    return NextResponse.json({
      running: dashboard.running ? stripPlanJson(dashboard.running) : null,
      queued: (dashboard.queued ?? []).map(stripPlanJson),
      recent_completed: (dashboard.recent_completed ?? []).map(stripPlanJson),
    });
  } catch (err) {
    // queue.db may not exist yet (no jobs ever enqueued)
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes("unable to open") || msg.includes("no such file")) {
      return NextResponse.json({ running: null, queued: [], recent_completed: [] });
    }
    return NextResponse.json(
      { error: "queue read failed", detail: sanitizeErrorDetail(msg) },
      { status: 502 },
    );
  }
}
