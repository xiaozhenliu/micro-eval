import path from "node:path";
import { NextResponse } from "next/server";
import Database from "better-sqlite3";
import { isServerMode } from "@/lib/server-mode";
import { resolveWorkspacePath } from "@/lib/workspace-api";

interface RouteContext {
  params: Promise<{ id: string }>;
}

interface TrendPoint {
  run_id: string;
  created_at: string;
  value: number | null;
  verdict: string | null;
  confidence: string | null;
  drift_break: boolean;
}

interface TrendSeries {
  configuration_id: string;
  metric: string;
  points: TrendPoint[];
  drift_count: number;
}

export async function GET(request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const { id } = await context.params;
  const wsPath = resolveWorkspacePath(id);
  if (!wsPath) return NextResponse.json({ error: "workspace not found" }, { status: 404 });

  const { searchParams } = new URL(request.url);
  const configId = searchParams.get("configuration_id");
  const metric = searchParams.get("metric") || "pass_rate";
  const limit = Math.min(parseInt(searchParams.get("limit") || "50", 10), 200);

  const dbPath = path.join(wsPath, ".micro-eval", "index.db");

  let db: InstanceType<typeof Database>;
  try {
    db = new Database(dbPath, { readonly: true });
  } catch {
    return NextResponse.json(
      { error: "No trend data available. Run evaluations first." },
      { status: 404 },
    );
  }

  try {
    if (configId) {
      const series = queryTrend(db, configId, metric, limit);
      return NextResponse.json(series);
    }

    const rows = db
      .prepare(
        "SELECT DISTINCT configuration_id FROM run_configurations ORDER BY configuration_id",
      )
      .all() as Array<{ configuration_id: string }>;

    const trends: TrendSeries[] = rows.map((row) =>
      queryTrend(db, row.configuration_id, metric, limit),
    );
    return NextResponse.json(trends);
  } finally {
    db.close();
  }
}

function queryTrend(
  db: InstanceType<typeof Database>,
  configurationId: string,
  metric: string,
  limit: number,
): TrendSeries {
  const metricColumn =
    metric === "mean_latency_ms"
      ? "rc.mean_latency_ms"
      : metric === "total_cost_amount"
        ? "rc.total_cost_amount"
        : "rc.pass_rate";

  const rows = db
    .prepare(
      `SELECT r.run_id, r.created_at, r.verdict, r.confidence, r.config_hash,
              ${metricColumn} as value
       FROM run_configurations rc
       JOIN runs r ON rc.run_id = r.run_id
       WHERE rc.configuration_id = ?
       ORDER BY r.created_at ASC
       LIMIT ?`,
    )
    .all(configurationId, limit) as Array<{
    run_id: string;
    created_at: string;
    verdict: string | null;
    confidence: string | null;
    config_hash: string;
    value: number | null;
  }>;

  let prevHash: string | null = null;
  const points: TrendPoint[] = rows.map((row) => {
    const driftBreak = prevHash !== null && row.config_hash !== prevHash;
    prevHash = row.config_hash;
    return {
      run_id: row.run_id,
      created_at: row.created_at,
      value: row.value,
      verdict: row.verdict,
      confidence: row.confidence,
      drift_break: driftBreak,
    };
  });

  return {
    configuration_id: configurationId,
    metric,
    points,
    drift_count: points.filter((p) => p.drift_break).length,
  };
}
