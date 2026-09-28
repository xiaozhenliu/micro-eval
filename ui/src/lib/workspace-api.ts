import path from "node:path";
import fs from "node:fs";
import { getServerDataRoot } from "./server-mode";
import { SAFE_SEGMENT_RE } from "./server-validation";

const WS_ID_RE = /^ws-\d{8}T\d{6}Z-[a-f0-9]{8}$/;

/**
 * Resolves a workspace id to its real, on-disk directory. Beyond the id
 * format and root-containment checks, this also rejects a workspace
 * directory that is itself a symlink and requires `workspace.json` inside it
 * to exist, not be a symlink, and declare the same `workspace_id` that was
 * requested — a same-root symlink (e.g. `workspaces/<other-id>` pointing at
 * `workspaces/<id>`) would otherwise pass the plain realpath-containment
 * check while silently serving a different workspace's data (round-6
 * review, 2026-09-12).
 */
export function resolveWorkspacePath(workspaceId: string): string | null {
  if (!WS_ID_RE.test(workspaceId)) return null;
  const dataRoot = getServerDataRoot();
  const wsDir = path.resolve(dataRoot, "workspaces", workspaceId);
  const wsRoot = path.resolve(dataRoot, "workspaces");
  if (!wsDir.startsWith(wsRoot + path.sep)) return null;
  try {
    if (fs.lstatSync(wsDir).isSymbolicLink()) return null;

    const realWsDir = fs.realpathSync(wsDir);
    const realWsRoot = fs.realpathSync(wsRoot);
    if (!realWsDir.startsWith(realWsRoot + path.sep)) return null;

    const metaPath = path.join(wsDir, "workspace.json");
    if (fs.lstatSync(metaPath).isSymbolicLink()) return null;
    const meta = JSON.parse(fs.readFileSync(metaPath, "utf-8")) as { workspace_id?: unknown };
    if (meta.workspace_id !== workspaceId) return null;

    return realWsDir;
  } catch {
    return null;
  }
}

/**
 * Resolves the `.micro-eval/runs` directory for a workspace. Rejects if
 * `.micro-eval` exists but is a symlink or not a directory, or if `runs`
 * exists but is a symlink — either would let a job with filesystem write
 * access to the workspace redirect run listings outside the workspace
 * (round-6 review, 2026-09-12). Neither path is required to exist yet: a
 * workspace with no runs recorded still resolves to the (non-existent)
 * canonical path, matching callers that check `fs.existsSync` first.
 */
export function getWorkspaceRunsDir(workspaceId: string): string | null {
  const wsPath = resolveWorkspacePath(workspaceId);
  if (!wsPath) return null;
  const microEvalDir = path.join(wsPath, ".micro-eval");
  const runsDir = path.join(microEvalDir, "runs");

  try {
    const microEvalStat = fs.lstatSync(microEvalDir);
    if (microEvalStat.isSymbolicLink() || !microEvalStat.isDirectory()) return null;
  } catch {
    // .micro-eval does not exist yet — no runs recorded, not a safety issue.
  }

  try {
    if (fs.lstatSync(runsDir).isSymbolicLink()) return null;
  } catch {
    // runs/ does not exist yet — same as above.
  }

  return runsDir;
}

/**
 * Resolves a single run directory inside a workspace's runs dir. `runId`
 * must be a safe path segment (mirrors the `RUN_ID_RE` checks that used to
 * be duplicated across every runs/[runId] route); the directory must exist,
 * must not itself be a symlink, and its realpath must stay under the
 * realpath of `runsDir` — closing the gap where a run directory replaced by
 * a symlink to an arbitrary outside path was served as-is (round-6 review,
 * 2026-09-12).
 */
export function resolveWorkspaceRunDir(workspaceId: string, runId: string): string | null {
  if (!SAFE_SEGMENT_RE.test(runId)) return null;
  const runsDir = getWorkspaceRunsDir(workspaceId);
  if (!runsDir) return null;

  const runDir = path.join(runsDir, runId);
  try {
    const runDirStat = fs.lstatSync(runDir);
    if (runDirStat.isSymbolicLink() || !runDirStat.isDirectory()) return null;

    const realRunsDir = fs.realpathSync(runsDir);
    const realRunDir = fs.realpathSync(runDir);
    if (!realRunDir.startsWith(realRunsDir + path.sep)) return null;

    return realRunDir;
  } catch {
    return null;
  }
}

/**
 * Resolves a path for a file inside an already-validated run directory
 * (`runDir`, as returned by `resolveWorkspaceRunDir`). Every `/`-separated
 * component of `relativePath` must be non-empty and not `.`/`..`, and no
 * component along the way (including the final one) may be a symlink — an
 * artifact whose recorded `path` was swapped for a symlink after the run
 * completed must not be followed outside the run directory (round-6
 * review, 2026-09-12). Returns the joined path, or null if any check fails.
 */
export function resolveInsideRunDir(runDir: string, relativePath: string): string | null {
  if (relativePath.includes("\\")) return null;
  const segments = relativePath.split("/");
  if (segments.length === 0) return null;
  for (const segment of segments) {
    if (segment === "" || segment === "." || segment === "..") return null;
  }

  let current = runDir;
  for (const segment of segments) {
    current = path.join(current, segment);
    try {
      if (fs.lstatSync(current).isSymbolicLink()) return null;
    } catch {
      return null;
    }
  }
  return current;
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
    // Same checks as a direct lookup: symlinked entries, symlinked
    // workspace.json and id mismatches are skipped rather than listed.
    const wsPath = resolveWorkspacePath(entry.name);
    if (!wsPath) continue;
    const metaPath = path.join(wsPath, "workspace.json");
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
