import path from "node:path";
import fs from "node:fs";
import { RunSchema, type Run } from "./schema";

export function getProjectRoot(): string {
  return (
    process.env.MICRO_EVAL_PROJECT_ROOT ||
    path.resolve(/* turbopackIgnore: true */ process.cwd(), "..")
  );
}

function getRunsDir(): string {
  return path.join(getProjectRoot(), ".micro-eval", "runs");
}

export async function listRuns(): Promise<Run[]> {
  const runsDir = getRunsDir();

  if (!fs.existsSync(runsDir)) {
    return [];
  }

  const files = fs.readdirSync(runsDir).filter((f) => f.endsWith(".json"));
  const runs: Run[] = [];

  for (const file of files) {
    try {
      const content = fs.readFileSync(path.join(runsDir, file), "utf-8");
      const data = JSON.parse(content);
      const parsed = RunSchema.parse(data);
      runs.push(parsed);
    } catch (err) {
      console.warn(`Skipping invalid run file: ${file}`, err);
    }
  }

  runs.sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  );

  return runs;
}

export async function getRun(id: string): Promise<Run | null> {
  const runsDir = getRunsDir();
  const filePath = path.join(runsDir, `${id}.json`);

  if (!fs.existsSync(filePath)) {
    return null;
  }

  try {
    const content = fs.readFileSync(filePath, "utf-8");
    const data = JSON.parse(content);
    return RunSchema.parse(data);
  } catch (err) {
    console.warn(`Failed to load run ${id}`, err);
    return null;
  }
}
