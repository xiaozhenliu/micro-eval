import { execFileSync } from "node:child_process";
import { NextResponse } from "next/server";
import { z } from "zod";
import { getRun, getProjectRoot } from "@/lib/api";
import { isServerMode } from "@/lib/server-mode";

const HumanEvaluationRequestSchema = z.object({
  pass_fail: z.enum(["pass", "fail"]).nullable().default(null),
  score: z.number().min(0).max(1).nullable().default(null),
  scores: z.record(z.string(), z.number()).default({}),
  comment: z.string().max(5000).default(""),
  evaluator: z.string().min(1).max(120).default("human"),
});

interface RouteContext {
  params: Promise<{ id: string; cellId: string }>;
}

export async function POST(request: Request, context: RouteContext) {
  // Local-only route: block in serve mode to prevent CSRF bypass (GRO-175 / M3).
  // Server-mode evaluations go through the workspace-scoped evaluate route.
  if (isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const { id, cellId } = await context.params;
  if (!/^(?!\.+$)[A-Za-z0-9_.:-]+$/.test(id)) return NextResponse.json({ error: "invalid run id" }, { status: 400 });
  const decodedCellId = decodeURIComponent(cellId);
  const run = await getRun(id);
  if (!run) return NextResponse.json({ error: "run not found" }, { status: 404 });
  if (!run.results.some((result) => result.cell_id === decodedCellId)) {
    return NextResponse.json({ error: "cell not found" }, { status: 404 });
  }

  let input;
  try {
    input = HumanEvaluationRequestSchema.parse(await request.json());
  } catch (error) {
    return NextResponse.json({ error: "invalid evaluation payload", detail: String(error) }, { status: 400 });
  }

  const uvBin = process.env.MICRO_EVAL_UV_PATH || "uv";
  const args = ["run", "micro-eval", "apply-evaluation", "--run-id", id, "--cell-id", decodedCellId];
  try {
    const stdout = execFileSync(uvBin, args, {
      input: JSON.stringify(input),
      encoding: "utf-8",
      cwd: getProjectRoot(),
      timeout: 30_000,
    });
    return NextResponse.json(JSON.parse(stdout));
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: "evaluation backend failed", detail }, { status: 502 });
  }
}
