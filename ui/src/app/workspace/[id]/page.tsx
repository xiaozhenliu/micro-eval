import Link from "next/link";
import { notFound } from "next/navigation";
import {
  readWorkspaceMeta,
  getWorkspaceRunsDir,
  resolveWorkspacePath,
  resolveWorkspaceRunDir,
  resolveInsideRunDir,
} from "@/lib/workspace-api";
import fs from "node:fs";
import { RunSchema } from "@/lib/schema";
import type { Run } from "@/lib/schema";
import { RunEnqueueButton } from "@/components/RunEnqueueButton";
import { readProjectDraft } from "@/lib/project-api";

interface PageProps {
  params: Promise<{ id: string }>;
}

function loadWorkspaceRuns(workspaceId: string): Run[] {
  const runsDir = getWorkspaceRunsDir(workspaceId);
  if (!runsDir || !fs.existsSync(runsDir)) return [];

  const entries = fs.readdirSync(runsDir, { withFileTypes: true });
  const runs: Run[] = [];

  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const runDir = resolveWorkspaceRunDir(workspaceId, entry.name);
    if (!runDir) continue;
    const runFile = resolveInsideRunDir(runDir, "run.json");
    if (!runFile || !fs.existsSync(runFile)) continue;
    try {
      const raw = JSON.parse(fs.readFileSync(runFile, "utf-8"));
      runs.push(RunSchema.parse(raw));
    } catch {
      // skip invalid
    }
  }

  return runs.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
}

interface SetupCounts {
  configurations: number;
  tasks: number;
  /** Configuration parse errors plus per-task parse errors (R8, round-6 review). */
  invalid: number;
  readable: boolean;
}

function loadSetupCounts(workspaceId: string): SetupCounts {
  const wsPath = resolveWorkspacePath(workspaceId);
  if (!wsPath) return { configurations: 0, tasks: 0, invalid: 0, readable: false };
  try {
    const draft = readProjectDraft(wsPath);
    // Only tasks that parsed cleanly count towards the setup gate; a broken
    // or missing task file would make build-plan fail after Enqueue.
    const usableTasks = draft.tasks.filter((entry) => entry.task !== null && !entry.error).length;
    // Configuration parse failures and per-task parse errors both make
    // build-plan fail after Enqueue too; surface their count so the gate
    // points the user at the Advanced tab instead of just showing 0s
    // (round-6 review, 2026-09-12).
    const invalid = draft.configuration_errors.length + draft.tasks.filter((entry) => entry.error).length;
    return { configurations: draft.configurations.length, tasks: usableTasks, invalid, readable: true };
  } catch {
    return { configurations: 0, tasks: 0, invalid: 0, readable: false };
  }
}

export default async function WorkspaceDetailPage({ params }: PageProps) {
  const { id } = await params;
  const meta = readWorkspaceMeta(id);
  if (!meta) notFound();

  const runs = loadWorkspaceRuns(id);
  const setup = loadSetupCounts(id);
  const disabledReason =
    meta.status !== "active"
      ? `Workspace is ${meta.status}; archived workspaces are read-only`
      : setup.invalid > 0
      ? `Fix ${setup.invalid} invalid entries in the Advanced tab first`
      : setup.configurations === 0 || setup.tasks === 0
        ? "Add at least one configuration and one task first"
        : undefined;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Link href="/" className="text-sm text-blue-400 hover:underline">← Home</Link>
          </div>
          <h2 className="text-xl font-semibold">{meta.name}</h2>
          {meta.description && (
            <p className="mt-1 text-sm text-neutral-400">{meta.description}</p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-neutral-500">
            <span className="rounded-full bg-neutral-800 px-2 py-0.5 text-neutral-300">{meta.status}</span>
            {meta.owner && <span>Owner: {meta.owner}</span>}
            {meta.template_id && <span>Template: {meta.template_id}</span>}
            <span>Created {new Date(meta.created_at).toLocaleDateString()}</span>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Link
            href={`/workspace/${id}/config`}
            className="rounded border border-neutral-700 px-3 py-1.5 text-sm text-neutral-300 hover:border-neutral-500 transition-colors"
          >
            Config
          </Link>
          <RunEnqueueButton workspaceId={id} disabledReason={disabledReason} />
        </div>
      </div>

      {/* Setup strip */}
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-neutral-800 px-4 py-3 text-sm">
        {!setup.readable && <span className="text-red-400">config unreadable</span>}
        <Link
          href={`/workspace/${id}/config?tab=configurations`}
          className={setup.configurations === 0 ? "text-amber-400 hover:underline" : "text-neutral-300 hover:underline"}
        >
          Configurations ({setup.configurations})
        </Link>
        <span className="text-neutral-600">→</span>
        <Link
          href={`/workspace/${id}/config?tab=tasks`}
          className={setup.tasks === 0 ? "text-amber-400 hover:underline" : "text-neutral-300 hover:underline"}
        >
          Tasks ({setup.tasks})
        </Link>
        {setup.invalid > 0 && (
          <>
            <span className="text-neutral-600">→</span>
            <Link href={`/workspace/${id}/config?tab=advanced`} className="text-red-400 hover:underline">
              {setup.invalid} invalid {setup.invalid === 1 ? "entry" : "entries"}
            </Link>
          </>
        )}
        <span className="text-neutral-600">→</span>
        <span className={disabledReason ? "text-neutral-600" : "text-neutral-300"}>Run</span>
      </div>

      {/* Runs */}
      <div>
        <h3 className="text-base font-medium mb-4">Runs ({runs.length})</h3>

        {runs.length === 0 ? (
          <div className="rounded-lg border border-neutral-800 py-12 text-center text-neutral-400">
            <p>No runs yet in this workspace.</p>
            <p className="mt-1 text-sm">Enqueue a run or run micro-eval from this workspace directory.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-neutral-800 text-neutral-400 text-left">
                  <th className="pb-3 pr-4 font-medium">Created</th>
                  <th className="pb-3 pr-4 font-medium">Status</th>
                  <th className="pb-3 pr-4 font-medium">Decision</th>
                  <th className="pb-3 pr-4 font-medium">Project</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id} className="border-b border-neutral-800/50 hover:bg-neutral-900/50">
                    <td className="py-3 pr-4">
                      <Link
                        href={`/workspace/${id}/run/${run.id}`}
                        className="text-blue-400 hover:underline"
                      >
                        {new Date(run.created_at).toLocaleString()}
                      </Link>
                    </td>
                    <td className="py-3 pr-4">{run.status}</td>
                    <td className="py-3 pr-4">{run.decision?.verdict ?? "inconclusive"}</td>
                    <td className="py-3 pr-4 text-neutral-400">{run.project_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
