import Link from "next/link";
import MemberBadge from "@/components/MemberBadge";

export interface WorkspaceMeta {
  workspace_id: string;
  name: string;
  owner: string;
  run_count: number;
  last_run_at: string | null;
  status: string;
  description?: string;
}

function formatTimestamp(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function statusColor(status: string): string {
  switch (status) {
    case "active":
      return "text-green-400";
    case "idle":
      return "text-neutral-400";
    case "error":
      return "text-red-400";
    default:
      return "text-neutral-400";
  }
}

export function WorkspaceCard({ workspace }: { workspace: WorkspaceMeta }) {
  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-lg p-4 hover:border-neutral-700 transition-colors">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <Link
            href={`/workspace/${workspace.workspace_id}`}
            className="text-blue-400 hover:underline font-medium truncate block"
          >
            {workspace.name}
          </Link>
          {workspace.description && (
            <p className="mt-1 text-sm text-neutral-400 line-clamp-2">
              {workspace.description}
            </p>
          )}
        </div>
        <span className={`text-xs font-medium shrink-0 ${statusColor(workspace.status)}`}>
          {workspace.status}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-neutral-400">
        <span>
          Owner: <MemberBadge name={workspace.owner} />
        </span>
        <span>{workspace.run_count} run{workspace.run_count !== 1 ? "s" : ""}</span>
        {workspace.last_run_at && (
          <span>Last run: {formatTimestamp(workspace.last_run_at)}</span>
        )}
      </div>
    </div>
  );
}
