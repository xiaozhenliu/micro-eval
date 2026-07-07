import { execFileSync } from "node:child_process";
import path from "node:path";
import fs from "node:fs";
import { NextResponse } from "next/server";
import { z } from "zod";
import { isServerMode } from "@/lib/server-mode";
import { getWorkspaceRunsDir, resolveWorkspacePath } from "@/lib/workspace-api";
import { RunSchema } from "@/lib/schema";
import { uvBin, validateWriteRequest, sanitizeErrorDetail } from "@/lib/server-validation";

interface RouteContext {
  params: Promise<{ id: string; runId: string; cellId: string }>;
}

const RUN_ID_RE = /^(?!\.+$)[A-Za-z0-9_.:-]+$/;

const HumanEvaluationRequestSchema = z.object({
  pass_fail: z.enum(["pass", "fail"]).nullable().default(null),
  score: z.number().min(0).max(1).nullable().default(null),
  scores: z.record(z.string(), z.number()).default({}),
  comment: z.string().max(5000).default(""),
  evaluator: z.string().min(1).max(120).default("human"),
});

export async function POST(request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const validation = validateWriteRequest(request);
  if (validation instanceof NextResponse) return validation;
  const { member } = validation;

  const { id, runId, cellId } = await context.params;
  if (!RUN_ID_RE.test(runId)) {
    return NextResponse.json({ error: "invalid run id" }, { status: 400 });
  }

  const wsPath = resolveWorkspacePath(id);
  if (!wsPath) return NextResponse.json({ error: "workspace not found" }, { status: 404 });

  const runsDir = getWorkspaceRunsDir(id);
  if (!runsDir) return NextResponse.json({ error: "workspace not found" }, { status: 404 });

  const runJsonPath = path.join(runsDir, runId, "run.json");
  if (!fs.existsSync(runJsonPath)) {
    return NextResponse.json({ error: "run not found" }, { status: 404 });
  }

  const decodedCellId = decodeURIComponent(cellId);

  try {
    const run = RunSchema.parse(JSON.parse(fs.readFileSync(runJsonPath, "utf-8")));
    if (!run.results.some((r) => r.cell_id === decodedCellId)) {
      return NextResponse.json({ error: "cell not found" }, { status: 404 });
    }
  } catch (err) {
    return NextResponse.json({ error: "failed to parse run", detail: sanitizeErrorDetail(String(err)) }, { status: 500 });
  }

  let input: z.infer<typeof HumanEvaluationRequestSchema>;
  try {
    const parsed = HumanEvaluationRequestSchema.parse(await request.json());
    input = { ...parsed, evaluator: member };
  } catch (err) {
    return NextResponse.json({ error: "invalid evaluation payload", detail: sanitizeErrorDetail(String(err)) }, { status: 400 });
  }

  const args = [
    "run", "micro-eval", "apply-evaluation",
    "--run-id", runId,
    "--cell-id", decodedCellId,
  ];

  try {
    const stdout = execFileSync(uvBin(), args, {
      input: JSON.stringify(input),
      encoding: "utf-8",
      cwd: wsPath,
      timeout: 30_000,
    });
    return NextResponse.json(JSON.parse(stdout));
  } catch (err) {
    const detail = sanitizeErrorDetail(err instanceof Error ? err.message : String(err));
    return NextResponse.json({ error: "evaluation backend failed", detail }, { status: 502 });
  }
}
