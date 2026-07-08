import path from "node:path";
import fs from "node:fs";
import { NextResponse } from "next/server";
import { isServerMode, getServerDataRoot } from "@/lib/server-mode";
import { listWorkspaces } from "@/lib/workspace-api";
import { queryQueue } from "@/lib/server-validation";

export async function GET() {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const dataRoot = getServerDataRoot();
  const workspaces = listWorkspaces();

  let queueStats: { queued: number; running: number } = { queued: 0, running: 0 };
  try {
    const dashboard = queryQueue(
      `result = db.get_queue_dashboard()\nprint(json.dumps(result))`,
    ) as { running: unknown | null; queued: unknown[] };
    queueStats = {
      queued: Array.isArray(dashboard.queued) ? dashboard.queued.length : 0,
      running: dashboard.running != null ? 1 : 0,
    };
  } catch {
    // queue.db may not exist — treat as empty
  }

  const templatesDir = path.join(dataRoot, "templates");
  let templateCount = 0;
  if (fs.existsSync(templatesDir)) {
    templateCount = fs.readdirSync(templatesDir, { withFileTypes: true }).filter(
      (e) => e.isDirectory(),
    ).length;
  }

  return NextResponse.json({
    server_mode: true,
    configured: true,
    workspace_count: workspaces.length,
    template_count: templateCount,
    queue: queueStats,
    ui_version: process.env.npm_package_version ?? "unknown",
  });
}
