import { execFileSync } from "node:child_process";
import { NextResponse } from "next/server";
import { isServerMode } from "@/lib/server-mode";
import { resolveWorkspacePath } from "@/lib/workspace-api";
import { uvBin, sanitizeErrorDetail } from "@/lib/server-validation";

interface RouteContext {
  params: Promise<{ id: string }>;
}

interface PlanCell {
  task: { id: string };
  configuration: { id: string };
  repetition: number;
}

interface PlanConfiguration {
  id: string;
  agent?: { command?: string[] };
}

interface RunPlan {
  cells?: PlanCell[];
  // The RunPlan JSON emitted by `build-plan` nests configurations inside each
  // cell rather than as a top-level list; agent commands are derived from cells.
}

/**
 * Read-only plan preview: builds the RunPlan for a workspace (same
 * `build-plan` CLI path the enqueue route uses) and reduces it to counts
 * the UI can render before a user commits to enqueueing a run.
 */
export async function GET(_request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const { id } = await context.params;
  const wsPath = resolveWorkspacePath(id);
  if (!wsPath) return NextResponse.json({ error: "workspace not found" }, { status: 404 });

  try {
    const planJson = execFileSync(
      uvBin(),
      ["run", "micro-eval", "build-plan", "--workspace", wsPath],
      { encoding: "utf-8", timeout: 30_000 },
    );
    const plan = JSON.parse(planJson) as RunPlan;
    const cells = plan.cells ?? [];

    const tasks = new Set(cells.map((c) => c.task.id));
    const configById = new Map<string, PlanConfiguration>();
    for (const cell of cells) {
      configById.set(cell.configuration.id, cell.configuration as PlanConfiguration);
    }
    const repetitions = cells.reduce((max, c) => Math.max(max, c.repetition), 0);
    const agentCommands = Array.from(configById.values()).map((c) =>
      (c.agent?.command ?? []).join(" "),
    );

    return NextResponse.json({
      tasks: tasks.size,
      configurations: configById.size,
      repetitions,
      total_cells: cells.length,
      agent_commands: agentCommands,
    });
  } catch (err) {
    const detail = sanitizeErrorDetail(err instanceof Error ? err.message : String(err));
    return NextResponse.json({ error: "failed to build plan summary", detail }, { status: 502 });
  }
}
