// @vitest-environment node
/**
 * GRO-555: the workspace create / update / delete routes must pass the
 * server data root to the CLI explicitly. `micro-eval workspace ...`
 * defaults `--data-root` to ~/.micro-eval-server and ignores both cwd and
 * MICRO_EVAL_DATA_ROOT, so a server started with a custom data root would
 * otherwise create workspaces it can never resolve.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const execFileSyncMock = vi.fn();

vi.mock("node:child_process", () => ({
  execFileSync: (...args: unknown[]) => execFileSyncMock(...args),
}));

const WS_ID = "ws-20260912T000000Z-abcdef01";
const DATA_ROOT = "/tmp/me-gro555-test-root";

vi.mock("@/lib/workspace-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/workspace-api")>();
  return {
    ...actual,
    readWorkspaceMeta: vi.fn(() => ({
      schema_version: "1.0",
      workspace_id: WS_ID,
      name: "demo",
      owner: "alice",
      template_id: null,
      template_version: null,
      created_at: "2026-09-12T00:00:00Z",
      last_run_at: null,
      run_count: 0,
      description: "",
      status: "active",
    })),
    resolveWorkspacePath: vi.fn(() => `${DATA_ROOT}/workspaces/${WS_ID}`),
  };
});

vi.mock("@/lib/server-validation", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/server-validation")>();
  return { ...actual, queryQueue: vi.fn(() => false) };
});

import { POST } from "@/app/api/workspaces/route";
import { PATCH, DELETE } from "@/app/api/workspaces/[id]/route";

function jsonRequest(url: string, method: string, body?: unknown): Request {
  return new Request(url, {
    method,
    headers: {
      "content-type": "application/json",
      "x-micro-eval-member": "alice",
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
}

function cliArgs(): string[] {
  expect(execFileSyncMock).toHaveBeenCalledTimes(1);
  const [, args] = execFileSyncMock.mock.calls[0] as [string, string[]];
  return args;
}

function dataRootArg(args: string[]): string | undefined {
  const idx = args.indexOf("--data-root");
  return idx === -1 ? undefined : args[idx + 1];
}

describe("GRO-555: workspace routes pass --data-root to the CLI", () => {
  const savedEnv = { ...process.env };

  beforeEach(() => {
    process.env.MICRO_EVAL_SERVER_MODE = "true";
    process.env.MICRO_EVAL_DATA_ROOT = DATA_ROOT;
    execFileSyncMock.mockReset();
  });

  afterEach(() => {
    process.env = { ...savedEnv };
  });

  it("POST /api/workspaces forwards the configured data root", async () => {
    execFileSyncMock.mockReturnValue(JSON.stringify({ workspace_id: WS_ID, name: "demo" }));

    const res = await POST(jsonRequest("http://localhost/api/workspaces", "POST", { name: "demo" }));

    expect(res.status).toBe(201);
    const args = cliArgs();
    expect(args.slice(0, 4)).toEqual(["run", "micro-eval", "workspace", "create"]);
    expect(dataRootArg(args)).toBe(DATA_ROOT);
  });

  it("PATCH /api/workspaces/[id] forwards the configured data root", async () => {
    execFileSyncMock.mockReturnValue(JSON.stringify({ workspace_id: WS_ID, name: "renamed" }));

    const res = await PATCH(
      jsonRequest(`http://localhost/api/workspaces/${WS_ID}`, "PATCH", { name: "renamed" }),
      { params: Promise.resolve({ id: WS_ID }) },
    );

    expect(res.status).toBe(200);
    const args = cliArgs();
    expect(args.slice(0, 5)).toEqual(["run", "micro-eval", "workspace", "update", WS_ID]);
    expect(dataRootArg(args)).toBe(DATA_ROOT);
  });

  it("DELETE /api/workspaces/[id] forwards the configured data root", async () => {
    execFileSyncMock.mockReturnValue("");

    const res = await DELETE(
      jsonRequest(`http://localhost/api/workspaces/${WS_ID}`, "DELETE"),
      { params: Promise.resolve({ id: WS_ID }) },
    );

    expect(res.status).toBe(200);
    const args = cliArgs();
    expect(args.slice(0, 5)).toEqual(["run", "micro-eval", "workspace", "delete", WS_ID]);
    expect(args).toContain("--force");
    expect(dataRootArg(args)).toBe(DATA_ROOT);
  });
});
