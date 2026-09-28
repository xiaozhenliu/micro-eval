// @vitest-environment node
/**
 * Round-6 review (R5/R6): unit tests for the workspace/run path resolvers in
 * lib/workspace-api.ts against a real filesystem — symlink checks cannot be
 * verified meaningfully with mocked fs calls, so these tests build actual
 * directories, files, and symlinks under a temp data root.
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  resolveWorkspacePath,
  getWorkspaceRunsDir,
  resolveWorkspaceRunDir,
  resolveInsideRunDir,
  listWorkspaces,
} from "../workspace-api";

const WS_ID_A = "ws-20260101T000000Z-aaaaaaaa";
const WS_ID_B = "ws-20260101T000000Z-bbbbbbbb";
const WS_ID_C = "ws-20260101T000000Z-cccccccc";

describe("workspace-api path resolvers (round-6 review, real filesystem)", () => {
  let tmpDir: string;
  let wsRoot: string;
  const savedEnv = { ...process.env };

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "micro-eval-ws-api-test-"));
    wsRoot = path.join(tmpDir, "workspaces");
    fs.mkdirSync(wsRoot, { recursive: true });
    process.env.MICRO_EVAL_DATA_ROOT = tmpDir;
  });

  afterEach(() => {
    process.env = { ...savedEnv };
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  function writeWorkspace(id: string): string {
    const dir = path.join(wsRoot, id);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "workspace.json"), JSON.stringify({ workspace_id: id, name: id }));
    return dir;
  }

  describe("listWorkspaces (round-7 review)", () => {
    it("lists only entries that pass the same checks as a direct lookup", () => {
      writeWorkspace(WS_ID_A);
      // B: same-root symlink to A (would list A's metadata under B).
      fs.symlinkSync(WS_ID_A, path.join(wsRoot, WS_ID_B), "dir");
      // C: real directory whose workspace.json is a symlink to A's.
      fs.mkdirSync(path.join(wsRoot, WS_ID_C));
      fs.symlinkSync(path.join(wsRoot, WS_ID_A, "workspace.json"), path.join(wsRoot, WS_ID_C, "workspace.json"));

      const listed = listWorkspaces(true).map((meta) => meta.workspace_id);
      expect(listed).toEqual([WS_ID_A]);
    });

    it("skips a directory whose metadata names a different workspace id", () => {
      writeWorkspace(WS_ID_A);
      const dirB = path.join(wsRoot, WS_ID_B);
      fs.mkdirSync(dirB);
      fs.writeFileSync(path.join(dirB, "workspace.json"), JSON.stringify({ workspace_id: WS_ID_A, name: "x" }));
      expect(listWorkspaces(true).map((meta) => meta.workspace_id)).toEqual([WS_ID_A]);
    });
  });

  describe("resolveWorkspacePath (R5)", () => {
    it("resolves a real workspace directory", () => {
      const dir = writeWorkspace(WS_ID_A);
      expect(resolveWorkspacePath(WS_ID_A)).toBe(fs.realpathSync(dir));
    });

    it("rejects a same-root symlink pointing at another workspace directory", () => {
      writeWorkspace(WS_ID_A);
      // B is a symlink to A, both under the same workspaces root — this
      // would pass the old realpath-containment check since the target is
      // still inside wsRoot.
      fs.symlinkSync(WS_ID_A, path.join(wsRoot, WS_ID_B), "dir");

      expect(resolveWorkspacePath(WS_ID_B)).toBeNull();
      // A itself must still resolve normally.
      expect(resolveWorkspacePath(WS_ID_A)).not.toBeNull();
    });

    it("rejects a workspace directory whose workspace.json is missing", () => {
      fs.mkdirSync(path.join(wsRoot, WS_ID_C), { recursive: true });
      expect(resolveWorkspacePath(WS_ID_C)).toBeNull();
    });

    it("rejects a workspace directory whose workspace.json is a symlink", () => {
      const dirA = writeWorkspace(WS_ID_A);
      const dirC = path.join(wsRoot, WS_ID_C);
      fs.mkdirSync(dirC, { recursive: true });
      fs.symlinkSync(path.join(dirA, "workspace.json"), path.join(dirC, "workspace.json"));

      expect(resolveWorkspacePath(WS_ID_C)).toBeNull();
    });

    it("rejects a workspace.json whose workspace_id does not match the requested id", () => {
      const dirC = path.join(wsRoot, WS_ID_C);
      fs.mkdirSync(dirC, { recursive: true });
      fs.writeFileSync(path.join(dirC, "workspace.json"), JSON.stringify({ workspace_id: WS_ID_A }));

      expect(resolveWorkspacePath(WS_ID_C)).toBeNull();
    });

    it("rejects an id that does not match the workspace id format", () => {
      expect(resolveWorkspacePath("not-a-workspace-id")).toBeNull();
    });
  });

  describe("getWorkspaceRunsDir (R6)", () => {
    it("returns the canonical runs path even when .micro-eval does not exist yet", () => {
      const dir = writeWorkspace(WS_ID_C);
      const runsDir = getWorkspaceRunsDir(WS_ID_C);
      expect(runsDir).toBe(path.join(fs.realpathSync(dir), ".micro-eval", "runs"));
      expect(fs.existsSync(runsDir!)).toBe(false);
    });

    it("returns the runs path when .micro-eval/runs exists normally", () => {
      const dir = writeWorkspace(WS_ID_C);
      fs.mkdirSync(path.join(dir, ".micro-eval", "runs"), { recursive: true });
      const runsDir = getWorkspaceRunsDir(WS_ID_C);
      expect(runsDir).not.toBeNull();
      expect(fs.existsSync(runsDir!)).toBe(true);
    });

    it("rejects when .micro-eval is a symlink", () => {
      const dir = writeWorkspace(WS_ID_C);
      const outside = fs.mkdtempSync(path.join(os.tmpdir(), "micro-eval-outside-"));
      fs.symlinkSync(outside, path.join(dir, ".micro-eval"), "dir");

      expect(getWorkspaceRunsDir(WS_ID_C)).toBeNull();
      fs.rmSync(outside, { recursive: true, force: true });
    });

    it("rejects when .micro-eval/runs is a symlink", () => {
      const dir = writeWorkspace(WS_ID_C);
      fs.mkdirSync(path.join(dir, ".micro-eval"), { recursive: true });
      const outside = fs.mkdtempSync(path.join(os.tmpdir(), "micro-eval-outside-"));
      fs.symlinkSync(outside, path.join(dir, ".micro-eval", "runs"), "dir");

      expect(getWorkspaceRunsDir(WS_ID_C)).toBeNull();
      fs.rmSync(outside, { recursive: true, force: true });
    });
  });

  describe("resolveWorkspaceRunDir (R6)", () => {
    it("resolves a real run directory", () => {
      const dir = writeWorkspace(WS_ID_C);
      const runDir = path.join(dir, ".micro-eval", "runs", "run-1");
      fs.mkdirSync(runDir, { recursive: true });

      expect(resolveWorkspaceRunDir(WS_ID_C, "run-1")).toBe(fs.realpathSync(runDir));
    });

    it("rejects a run id that fails the safe-segment check", () => {
      writeWorkspace(WS_ID_C);
      expect(resolveWorkspaceRunDir(WS_ID_C, "..")).toBeNull();
      expect(resolveWorkspaceRunDir(WS_ID_C, "../escape")).toBeNull();
    });

    it("returns null when the run directory does not exist", () => {
      writeWorkspace(WS_ID_C);
      expect(resolveWorkspaceRunDir(WS_ID_C, "missing-run")).toBeNull();
    });

    it("returns 404-worthy null when a run directory is replaced by a symlink to an outside directory", () => {
      const dir = writeWorkspace(WS_ID_C);
      const runsDir = path.join(dir, ".micro-eval", "runs");
      fs.mkdirSync(runsDir, { recursive: true });
      const outside = fs.mkdtempSync(path.join(os.tmpdir(), "micro-eval-outside-run-"));
      fs.writeFileSync(path.join(outside, "secret.txt"), "leaked");
      fs.symlinkSync(outside, path.join(runsDir, "run-1"), "dir");

      expect(resolveWorkspaceRunDir(WS_ID_C, "run-1")).toBeNull();
      fs.rmSync(outside, { recursive: true, force: true });
    });
  });

  describe("resolveInsideRunDir (R6)", () => {
    function makeRunDir(): string {
      const dir = writeWorkspace(WS_ID_C);
      const runDir = path.join(dir, ".micro-eval", "runs", "run-1");
      fs.mkdirSync(runDir, { recursive: true });
      return fs.realpathSync(runDir);
    }

    it("resolves a plain file inside the run directory", () => {
      const runDir = makeRunDir();
      fs.writeFileSync(path.join(runDir, "run.json"), "{}");
      expect(resolveInsideRunDir(runDir, "run.json")).toBe(path.join(runDir, "run.json"));
    });

    it("resolves a nested relative path", () => {
      const runDir = makeRunDir();
      fs.mkdirSync(path.join(runDir, "sub"), { recursive: true });
      fs.writeFileSync(path.join(runDir, "sub", "file.txt"), "hi");
      expect(resolveInsideRunDir(runDir, "sub/file.txt")).toBe(path.join(runDir, "sub", "file.txt"));
    });

    it("rejects '..' traversal components", () => {
      const runDir = makeRunDir();
      expect(resolveInsideRunDir(runDir, "../escape.txt")).toBeNull();
      expect(resolveInsideRunDir(runDir, "sub/../../escape.txt")).toBeNull();
    });

    it("rejects an empty path component", () => {
      const runDir = makeRunDir();
      fs.mkdirSync(path.join(runDir, "sub"), { recursive: true });
      expect(resolveInsideRunDir(runDir, "sub//file.txt")).toBeNull();
    });

    it("rejects backslashes outright", () => {
      const runDir = makeRunDir();
      expect(resolveInsideRunDir(runDir, "sub\\file.txt")).toBeNull();
    });

    it("rejects when the target itself is a symlink", () => {
      const runDir = makeRunDir();
      const outside = fs.mkdtempSync(path.join(os.tmpdir(), "micro-eval-outside-artifact-"));
      fs.writeFileSync(path.join(outside, "leaked.txt"), "leaked");
      fs.symlinkSync(path.join(outside, "leaked.txt"), path.join(runDir, "artifact.txt"));

      expect(resolveInsideRunDir(runDir, "artifact.txt")).toBeNull();
      fs.rmSync(outside, { recursive: true, force: true });
    });

    it("rejects when an intermediate directory component is a symlink", () => {
      const runDir = makeRunDir();
      const outside = fs.mkdtempSync(path.join(os.tmpdir(), "micro-eval-outside-dir-"));
      fs.writeFileSync(path.join(outside, "file.txt"), "leaked");
      fs.symlinkSync(outside, path.join(runDir, "sublink"), "dir");

      expect(resolveInsideRunDir(runDir, "sublink/file.txt")).toBeNull();
      fs.rmSync(outside, { recursive: true, force: true });
    });

    it("returns null when relativePath is empty", () => {
      const runDir = makeRunDir();
      expect(resolveInsideRunDir(runDir, "")).toBeNull();
    });
  });
});
