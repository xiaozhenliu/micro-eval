import { execFileSync } from "node:child_process";
import { NextResponse } from "next/server";
import { isServerMode, getServerDataRoot } from "@/lib/server-mode";
import { resolveWorkspacePath } from "@/lib/workspace-api";
import { uvBin, sanitizeErrorDetail, sanitizePlanBuildDetail, redactDeclaredSecrets, parseCliRefusal } from "@/lib/server-validation";
import { INVALID_GIT_REF_REASON, INVALID_GIT_REF_HINT } from "@/lib/refusal-hints";

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
  // The RunPlan JSON nests configurations inside each cell rather than as a
  // top-level list; agent commands are derived from cells.
}

interface DryRun {
  plan_digest?: unknown;
  plan?: RunPlan;
}


/**
 * Read-only plan preview: `workspace enqueue --dry-run` builds the plan with
 * exactly the loader, admission rules and digest the real enqueue uses
 * (round-8 review, 2026-09-13), and this route reduces it to counts the UI
 * can render before a user commits to enqueueing a run.
 */
export async function GET(_request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const { id } = await context.params;
  const wsPath = resolveWorkspacePath(id);
  if (!wsPath) return NextResponse.json({ error: "workspace not found" }, { status: 404 });

  let dryRun: DryRun;
  try {
    const stdout = execFileSync(
      uvBin(),
      ["run", "micro-eval", "workspace", "enqueue", id, "--dry-run", "--data-root", getServerDataRoot()],
      // Plans embed every task verbatim; the default 1 MiB maxBuffer is too small.
      { encoding: "utf-8", timeout: 30_000, maxBuffer: 16 * 1024 * 1024 },
    );
    dryRun = JSON.parse(stdout.trim()) as DryRun;
  } catch (err) {
    const refusal = parseCliRefusal(err);
    if (refusal?.error === "workspace_not_active") {
      return NextResponse.json(
        { error: `workspace is ${String(refusal.status)}; only active workspaces can enqueue runs` },
        { status: 409 },
      );
    }
    if (refusal?.error === "workspace_not_found") {
      return NextResponse.json({ error: "workspace not found" }, { status: 404 });
    }
    const detail = refusal?.error === "plan_build_failed"
      ? sanitizePlanBuildDetail(String(refusal.detail ?? ""))
      : redactDeclaredSecrets(sanitizeErrorDetail(err instanceof Error ? err.message : String(err)));
    const body: Record<string, unknown> = { error: "failed to build plan summary", detail };
    // Same fixed hint contract as the enqueue route: only the known
    // structured reason, never an arbitrary backend hint (GRO-972).
    if (refusal?.error === "plan_build_failed" && refusal.reason === INVALID_GIT_REF_REASON) {
      body.reason = INVALID_GIT_REF_REASON;
      body.hint = INVALID_GIT_REF_HINT;
    }
    return NextResponse.json(body, { status: 502 });
  }

  try {
    const plan = dryRun.plan ?? {};
    const cells = plan.cells ?? [];

    const tasks = new Set(cells.map((c) => c.task.id));
    const configById = new Map<string, PlanConfiguration>();
    for (const cell of cells) {
      configById.set(cell.configuration.id, cell.configuration as PlanConfiguration);
    }
    // Repetitions are per configuration; the tasks × configs × reps formula
    // only holds when every configuration uses the same count.
    const repsByConfig = new Map<string, number>();
    for (const cell of cells) {
      repsByConfig.set(cell.configuration.id, Math.max(repsByConfig.get(cell.configuration.id) ?? 0, cell.repetition));
    }
    const repValues = Array.from(repsByConfig.values());
    const repetitions = repValues.reduce((max, value) => Math.max(max, value), 0);
    const repetitionsUniform = repValues.every((value) => value === repetitions);
    // A command line may carry a pasted secret; never show declared secret
    // values in the preview (round-5 review, 2026-09-12).
    const agentCommands = Array.from(configById.values()).map((c) =>
      redactDeclaredSecrets((c.agent?.command ?? []).join(" ")),
    );

    const digest = dryRun.plan_digest;
    return NextResponse.json({
      tasks: tasks.size,
      configurations: configById.size,
      repetitions,
      repetitions_uniform: repetitionsUniform,
      total_cells: cells.length,
      agent_commands: agentCommands,
      // Admission digest computed by the CLI over the whole plan (tasks,
      // configurations, guardrails, output_dir, ...); the enqueue call
      // refuses when it no longer matches (round-6/7/8 reviews).
      plan_digest: typeof digest === "string" && digest.length > 0 ? digest : null,
    });
  } catch (err) {
    const detail = sanitizeErrorDetail(err instanceof Error ? err.message : String(err));
    return NextResponse.json({ error: "failed to build plan summary", detail }, { status: 502 });
  }
}
