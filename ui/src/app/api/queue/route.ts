import { NextResponse } from "next/server";
import { isServerMode } from "@/lib/server-mode";
import { queryQueue } from "@/lib/server-validation";

export async function GET() {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  try {
    const dashboard = queryQueue(
      `result = db.get_queue_dashboard()\nprint(json.dumps(result))`,
    );
    return NextResponse.json(dashboard);
  } catch (err) {
    // queue.db may not exist yet (no jobs ever enqueued)
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes("unable to open") || msg.includes("no such file")) {
      return NextResponse.json({ running: null, queued: [], recent_completed: [] });
    }
    return NextResponse.json(
      { error: "queue read failed", detail: msg },
      { status: 502 },
    );
  }
}
