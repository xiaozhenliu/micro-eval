import { execFileSync } from "node:child_process";
import { NextResponse } from "next/server";
import { isServerMode, getServerDataRoot } from "@/lib/server-mode";
import { resolveWorkspacePath } from "@/lib/workspace-api";
import { validateWriteRequest, uvBin } from "@/lib/server-validation";

interface RouteContext {
  params: Promise<{ id: string }>;
}

export async function POST(request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const validation = validateWriteRequest(request);
  if (validation instanceof NextResponse) return validation;
  const { member } = validation;

  const { id } = await context.params;
  const wsPath = resolveWorkspacePath(id);
  if (!wsPath) return NextResponse.json({ error: "workspace not found" }, { status: 404 });

  // Step 1: Build the run plan for this workspace
  let planJson: string;
  try {
    planJson = execFileSync(
      uvBin(),
      ["run", "micro-eval", "build-plan", "--workspace", wsPath],
      {
        encoding: "utf-8",
        timeout: 30_000,
      },
    );
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: "failed to build run plan", detail }, { status: 502 });
  }

  // Step 2: Enqueue the plan via Python (queue.db lives in data root)
  const dataRoot = getServerDataRoot();
  const enqueueScript = `
import json, sys, os
sys.path.insert(0, '.')
from micro_eval.server.queue import QueueDB, QueueFullError
plan_json = sys.stdin.read().strip()
db = QueueDB(os.environ['_QUEUE_DB_PATH'])
try:
    result = db.enqueue(
        workspace_id=os.environ['_WS_ID'],
        owner=os.environ['_OWNER'],
        plan_json=plan_json,
    )
    print(json.dumps(result))
except QueueFullError as e:
    print(json.dumps({"error": "queue_full", "current": e.current, "maximum": e.maximum}))
    sys.exit(2)
finally:
    db.close()
`;

  try {
    const stdout = execFileSync(uvBin(), ["run", "python", "-c", enqueueScript], {
      input: planJson,
      encoding: "utf-8",
      timeout: 10_000,
      env: {
        ...process.env,
        _QUEUE_DB_PATH: dataRoot + "/queue.db",
        _WS_ID: id,
        _OWNER: member,
      },
    });
    const result = JSON.parse(stdout.trim()) as Record<string, unknown>;
    if (result.error === "queue_full") {
      return NextResponse.json(result, { status: 429 });
    }
    return NextResponse.json(result, { status: 202 });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: "enqueue failed", detail }, { status: 502 });
  }
}
