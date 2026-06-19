import path from "node:path";
import fs from "node:fs";
import { getServerDataRoot } from "./server-mode";

const WS_ID_RE = /^ws-\d{8}T\d{6}Z-[a-f0-9]{8}$/;

export function resolveWorkspacePath(workspaceId: string): string | null {
  if (!WS_ID_RE.test(workspaceId)) return null;
  const dataRoot = getServerDataRoot();
  const wsDir = path.resolve(dataRoot, "workspaces", workspaceId);
  const wsRoot = path.resolve(dataRoot, "workspaces");
  if (!wsDir.startsWith(wsRoot + path.sep)) return null;
  try {
    const realWsDir = fs.realpathSync(wsDir);
    const realWsRoot = fs.realpathSync(wsRoot);
    if (!realWsDir.startsWith(realWsRoot + path.sep)) return null;
    return realWsDir;
  } catch {
    return null;
  }
}

export function getWorkspaceRunsDir(workspaceId: string): string | null {
  const wsPath = resolveWorkspacePath(workspaceId);
  if (!wsPath) return null;
  return path.join(wsPath, ".micro-eval", "runs");
}

export interface WorkspaceMeta {
  schema_version: string;
  workspace_id: string;
  name: string;
  owner: string;
  template_id: string | null;
  template_version: string | null;
  created_at: string;
  last_run_at: string | null;
  run_count: number;
  description: string;
  status: string;
}

export function readWorkspaceMeta(workspaceId: string): WorkspaceMeta | null {
  const wsPath = resolveWorkspacePath(workspaceId);
  if (!wsPath) return null;
  const metaPath = path.join(wsPath, "workspace.json");
  if (!fs.existsSync(metaPath)) return null;
  return JSON.parse(fs.readFileSync(metaPath, "utf-8"));
}

export function listWorkspaces(includeArchived = false): WorkspaceMeta[] {
  const wsRoot = path.join(getServerDataRoot(), "workspaces");
  if (!fs.existsSync(wsRoot)) return [];
  const entries = fs.readdirSync(wsRoot, { withFileTypes: true });
  const result: WorkspaceMeta[] = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const metaPath = path.join(wsRoot, entry.name, "workspace.json");
    if (!fs.existsSync(metaPath)) continue;
    try {
      const meta: WorkspaceMeta = JSON.parse(fs.readFileSync(metaPath, "utf-8"));
      if (!includeArchived && meta.status === "archived") continue;
      result.push(meta);
    } catch {
      continue;
    }
  }
  return result.sort((a, b) => b.created_at.localeCompare(a.created_at));
}
