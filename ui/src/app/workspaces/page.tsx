import Link from "next/link";
import { listWorkspaces } from "@/lib/workspace-api";
import type { WorkspaceMeta } from "@/lib/workspace-api";

export const dynamic = "force-dynamic";

function WorkspaceRow({ workspace }: { workspace: WorkspaceMeta }) {
  return (
    <tr className="border-b border-neutral-800/50 hover:bg-neutral-900/50">
      <td className="py-3 pr-4">
        <Link href={`/workspace/${workspace.workspace_id}`} className="text-blue-400 hover:underline font-medium">
          {workspace.name}
        </Link>
        {workspace.description && (
          <p className="mt-0.5 text-xs text-neutral-500 truncate max-w-xs">{workspace.description}</p>
        )}
      </td>
      <td className="py-3 pr-4 text-sm text-neutral-300">{workspace.owner || "—"}</td>
      <td className="py-3 pr-4 text-sm">
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
          workspace.status === "active"
            ? "bg-green-950/50 text-green-400"
            : workspace.status === "archived"
            ? "bg-neutral-800 text-neutral-500"
            : "bg-neutral-800 text-neutral-300"
        }`}>
          {workspace.status}
        </span>
      </td>
      <td className="py-3 pr-4 text-sm text-neutral-400">{workspace.run_count}</td>
      <td className="py-3 pr-4 text-sm text-neutral-400">
        {workspace.last_run_at ? new Date(workspace.last_run_at).toLocaleString() : "—"}
      </td>
      <td className="py-3 text-sm text-neutral-400">
        {new Date(workspace.created_at).toLocaleDateString()}
      </td>
    </tr>
  );
}

export default function WorkspacesPage() {
  const workspaces = listWorkspaces(true);

  const active = workspaces.filter((ws) => ws.status !== "archived");
  const archived = workspaces.filter((ws) => ws.status === "archived");

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">All Workspaces</h2>
          <p className="mt-1 text-sm text-neutral-400">
            {active.length} active · {archived.length} archived
          </p>
        </div>
        <Link
          href="/workspaces/new"
          className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
        >
          New Workspace
        </Link>
      </div>

      {workspaces.length === 0 ? (
        <div className="rounded-lg border border-neutral-800 py-16 text-center text-neutral-400">
          <p className="text-lg">No workspaces found.</p>
          <p className="mt-2 text-sm">
            <Link href="/workspaces/new" className="text-blue-400 hover:underline">
              Create a workspace
            </Link>{" "}
            to get started.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-neutral-800 text-neutral-400 text-left">
                <th className="pb-3 pr-4 font-medium">Name</th>
                <th className="pb-3 pr-4 font-medium">Owner</th>
                <th className="pb-3 pr-4 font-medium">Status</th>
                <th className="pb-3 pr-4 font-medium">Runs</th>
                <th className="pb-3 pr-4 font-medium">Last Run</th>
                <th className="pb-3 font-medium">Created</th>
              </tr>
            </thead>
            <tbody>
              {workspaces.map((ws) => (
                <WorkspaceRow key={ws.workspace_id} workspace={ws} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
