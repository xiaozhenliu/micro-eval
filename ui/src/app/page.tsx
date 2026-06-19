import Link from "next/link";
import { listRuns } from "@/lib/api";
import { RunList } from "@/components/RunList";
import { WorkspaceCard } from "@/components/WorkspaceCard";
import { isServerMode } from "@/lib/server-mode";
import { listWorkspaces } from "@/lib/workspace-api";

async function ServerDashboard() {
  const workspaces = listWorkspaces(false);

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">Workspaces</h2>
          <p className="mt-1 text-sm text-neutral-400">
            {workspaces.length} active workspace{workspaces.length !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/queue"
            className="rounded border border-neutral-700 px-3 py-1.5 text-sm text-neutral-300 hover:border-neutral-500 transition-colors"
          >
            Queue
          </Link>
          <Link
            href="/workspaces/new"
            className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
          >
            New Workspace
          </Link>
        </div>
      </div>

      {workspaces.length === 0 ? (
        <div className="rounded-lg border border-neutral-800 py-16 text-center text-neutral-400">
          <p className="text-lg">No workspaces yet.</p>
          <p className="mt-2 text-sm">
            <Link href="/workspaces/new" className="text-blue-400 hover:underline">
              Create your first workspace
            </Link>{" "}
            to get started.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {workspaces.map((ws) => (
            <WorkspaceCard key={ws.workspace_id} workspace={ws} />
          ))}
        </div>
      )}

      <div className="border-t border-neutral-800 pt-6">
        <div className="flex items-center justify-between gap-4 mb-4">
          <h3 className="text-base font-medium text-neutral-300">Quick Links</h3>
        </div>
        <div className="flex flex-wrap gap-3 text-sm">
          <Link href="/workspaces" className="text-blue-400 hover:underline">All workspaces (incl. archived)</Link>
          <span className="text-neutral-700">·</span>
          <Link href="/templates" className="text-blue-400 hover:underline">Templates</Link>
          <span className="text-neutral-700">·</span>
          <Link href="/queue" className="text-blue-400 hover:underline">Run queue</Link>
        </div>
      </div>
    </div>
  );
}

export default async function HomePage() {
  if (isServerMode()) {
    return <ServerDashboard />;
  }

  const runs = await listRuns();

  return (
    <div>
      <h2 className="text-xl font-semibold mb-6">Runs</h2>
      <RunList runs={runs} />
    </div>
  );
}
