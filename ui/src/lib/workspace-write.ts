import { readWorkspaceMeta, resolveWorkspacePath } from "@/lib/workspace-api";
/**
 * Resolve a workspace for a browser-side write. Archived workspaces are
 * read-only (round-10 review, 2026-09-13): returns the reason instead of a
 * path so routes answer 409 before touching the CLI.
 */
export function resolveWritableWorkspace(
  workspaceId: string,
): { wsPath: string } | { error: string; status: 404 | 409 } {
  const meta = readWorkspaceMeta(workspaceId);
  if (!meta) return { error: "workspace not found", status: 404 };
  if (meta.status !== "active") {
    return { error: `workspace is ${meta.status}; archived workspaces are read-only`, status: 409 };
  }
  const wsPath = resolveWorkspacePath(workspaceId);
  if (!wsPath) return { error: "workspace not found", status: 404 };
  return { wsPath };
}
