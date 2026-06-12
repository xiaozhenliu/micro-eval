import path from "node:path";
import fs from "node:fs";
import { DecisionReportSchema, RunSchema, type ArtifactRef, type CellResult, type Run, type TraceRef } from "./schema";

export function getProjectRoot(): string {
  return (
    process.env.MICRO_EVAL_PROJECT_ROOT ||
    path.resolve(/* turbopackIgnore: true */ process.cwd(), "..")
  );
}

export function getRunsDir(): string {
  return path.join(getProjectRoot(), ".micro-eval", "runs");
}

function safeId(id: string): string | null {
  return /^[A-Za-z0-9_.:-]+$/.test(id) ? id : null;
}

export async function listRuns(): Promise<Run[]> {
  const runsDir = getRunsDir();

  if (!fs.existsSync(runsDir)) {
    return [];
  }

  const entries = fs.readdirSync(runsDir, { withFileTypes: true });
  const runs: Run[] = [];

  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    try {
      const runDir = path.join(runsDir, entry.name);
      const content = fs.readFileSync(path.join(runDir, "run.json"), "utf-8");
      runs.push(parseRunWithDecision(JSON.parse(content), runDir));
    } catch (err) {
      console.warn(`Skipping invalid run directory: ${entry.name}`, err);
    }
  }

  runs.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  return runs;
}

export async function getRun(id: string): Promise<Run | null> {
  const safe = safeId(id);
  if (!safe) return null;
  const filePath = path.join(getRunsDir(), safe, "run.json");

  if (!fs.existsSync(filePath)) {
    return null;
  }

  try {
    const content = fs.readFileSync(filePath, "utf-8");
    return parseRunWithDecision(JSON.parse(content), path.dirname(filePath));
  } catch (err) {
    console.warn(`Failed to load run ${id}`, err);
    return null;
  }
}

export function getRunDir(id: string): string | null {
  const safe = safeId(id);
  if (!safe) return null;
  return path.join(getRunsDir(), safe);
}

export function saveRun(run: Run): void {
  const runDir = getRunDir(run.id);
  if (!runDir) throw new Error("invalid run id");
  fs.mkdirSync(runDir, { recursive: true });
  fs.writeFileSync(path.join(runDir, "run.json"), JSON.stringify(run, null, 2));
  if (run.decision) {
    fs.writeFileSync(path.join(runDir, "decision.json"), JSON.stringify(run.decision, null, 2));
  }
}

function parseRunWithDecision(raw: unknown, runDir: string): Run {
  const run = RunSchema.parse(raw);
  const decisionPath = path.join(runDir, "decision.json");
  if (!fs.existsSync(decisionPath)) return run;
  const decision = DecisionReportSchema.parse(JSON.parse(fs.readFileSync(decisionPath, "utf-8")));
  return { ...run, decision };
}

export async function getCell(runId: string, cellId: string): Promise<CellResult | null> {
  const run = await getRun(runId);
  if (!run) return null;
  return run.results.find((result) => result.cell_id === cellId) ?? null;
}

export async function getArtifact(runId: string, artifactId: string): Promise<{ artifact: ArtifactRef; content: string } | null> {
  const run = await getRun(runId);
  const safe = safeId(runId);
  if (!run || !safe) return null;
  const artifact = run.artifacts.find((item) => item.artifact_id === artifactId);
  if (!artifact) return null;

  const runDir = path.join(getRunsDir(), safe);
  const artifactPath = path.resolve(runDir, artifact.path);
  if (!artifactPath.startsWith(path.resolve(runDir) + path.sep)) return null;
  if (!fs.existsSync(artifactPath)) return null;
  const realRunDir = fs.realpathSync(runDir);
  const realArtifactPath = fs.realpathSync(artifactPath);
  if (!realArtifactPath.startsWith(realRunDir + path.sep)) return null;
  if (artifact.warning?.includes("skipped_oversized")) {
    return { artifact, content: `[${artifact.warning}: ${artifact.path}]` };
  }
  if (artifact.media_type !== "text/plain") {
    return { artifact, content: `[${artifact.warning ?? "non-text artifact not displayed"}: ${artifact.path}]` };
  }

  return { artifact, content: fs.readFileSync(realArtifactPath, "utf-8") };
}


export async function getCellTrace(runId: string, cellId: string): Promise<TraceRef[]> {
  const run = await getRun(runId);
  if (!run) return [];
  const cell = run.results.find((result) => result.cell_id === cellId);
  if (!cell) return [];
  const traceByRef = new Map(run.traces.map((trace) => [`${trace.provider}:${trace.trace_id}`, trace]));
  return cell.trace_refs.map((traceRef) => traceByRef.get(traceRef)).filter((trace): trace is TraceRef => trace != null);
}
