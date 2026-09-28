// @vitest-environment node
/**
 * Round-3 review N7: a JSON body of `null` (or a non-object) must be a 400,
 * not a TypeError-driven 500, on PUT /api/workspaces/[id]/config.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const WS_ID = "ws-20260912T000000Z-abcdef01";

vi.mock("@/lib/workspace-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/workspace-api")>();
  return {
    ...actual,
    resolveWorkspacePath: vi.fn(() => `/tmp/root/workspaces/${WS_ID}`),
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
  };
});

const writeRawConfigMock = vi.fn();
vi.mock("@/lib/project-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/project-api")>();
  return { ...actual, writeRawConfig: (...args: unknown[]) => writeRawConfigMock(...args) };
});

import { PUT } from "@/app/api/workspaces/[id]/config/route";

function put(body: string): Request {
  return new Request(`http://localhost/api/workspaces/${WS_ID}/config`, {
    method: "PUT",
    headers: { "content-type": "application/json", "x-micro-eval-member": "alice" },
    body,
  });
}

describe("PUT /api/workspaces/[id]/config body validation", () => {
  const savedEnv = { ...process.env };
  beforeEach(() => {
    process.env.MICRO_EVAL_SERVER_MODE = "true";
    writeRawConfigMock.mockReset();
  });
  afterEach(() => {
    process.env = { ...savedEnv };
  });

  it.each(["null", "42", '"text"', "[]", "{}", '{"content": 5}'])("rejects body %s with 400", async (body) => {
    const res = await PUT(put(body), { params: Promise.resolve({ id: WS_ID }) });
    expect(res.status).toBe(400);
    expect(writeRawConfigMock).not.toHaveBeenCalled();
  });

  it("forwards a string content to writeRawConfig", async () => {
    const res = await PUT(put('{"content": "project_name: x\\n"}'), { params: Promise.resolve({ id: WS_ID }) });
    expect(res.status).toBe(200);
    expect(writeRawConfigMock).toHaveBeenCalledWith(`/tmp/root/workspaces/${WS_ID}`, "project_name: x\n", "alice");
  });
});
