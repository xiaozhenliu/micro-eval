import { NextResponse } from "next/server";
import { z } from "zod";
import { getRun, getRunDir, saveRun } from "@/lib/api";
import { appendEvaluationFile, appendEvaluationToRun, buildHumanEvaluation } from "@/lib/evaluation";

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
  const { id, cellId } = await context.params;
  const decodedCellId = decodeURIComponent(cellId);
  const run = await getRun(id);
  const runDir = getRunDir(id);
  if (!run || !runDir) return NextResponse.json({ error: "run not found" }, { status: 404 });
  if (!run.results.some((result) => result.cell_id === decodedCellId)) {
    return NextResponse.json({ error: "cell not found" }, { status: 404 });
  }

  let input;
  try {
    input = HumanEvaluationRequestSchema.parse(await request.json());
  } catch (error) {
    return NextResponse.json({ error: "invalid evaluation payload", detail: String(error) }, { status: 400 });
  }

  const { evaluation, evidence } = buildHumanEvaluation(decodedCellId, input);
  appendEvaluationFile(runDir, decodedCellId, evaluation);
  const updatedRun = appendEvaluationToRun(run, evaluation, evidence);
  saveRun(updatedRun);
  return NextResponse.json({ evaluation, evidence, decision: updatedRun.decision });
}
