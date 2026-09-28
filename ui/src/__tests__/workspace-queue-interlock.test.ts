// @vitest-environment node
/**
 * Round-5/6/7 reviews: workspace/queue interlock and plan-preview redaction.
 * - archiving or deleting a workspace with pending jobs is refused (409)
 * - enqueueing into a non-active workspace is refused (409)
 * - enqueue goes through the locked `workspace enqueue` CLI; its JSON
 *   refusals map to 409/429/502
 * - plan-summary never shows declared secret values in agent commands
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const WS_ID = "ws-20260912T000000Z-abcdef01";
const queryQueueMock = vi.fn();
const execFileSyncMock = vi.fn();
let metaStatus = "active";

vi.mock("node:child_process", () => ({ execFileSync: (...args: unknown[]) => execFileSyncMock(...args) }));

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
      status: metaStatus,
    })),
    resolveWorkspacePath: vi.fn(() => `/tmp/root/workspaces/${WS_ID}`),
  };
});

vi.mock("@/lib/server-validation", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/server-validation")>();
  return { ...actual, queryQueue: (...args: unknown[]) => queryQueueMock(...args) };
});

import { PATCH, DELETE } from "@/app/api/workspaces/[id]/route";
import { POST as enqueue } from "@/app/api/workspaces/[id]/runs/enqueue/route";
import { GET as planSummary } from "@/app/api/workspaces/[id]/plan-summary/route";
import { PUT as putConfiguration } from "@/app/api/workspaces/[id]/project/configurations/route";

function jsonRequest(method: string, body?: unknown): Request {
  return new Request(`http://localhost/api/workspaces/${WS_ID}`, {
    method,
    headers: { "content-type": "application/json", "x-micro-eval-member": "alice" },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
}

const ctx = { params: Promise.resolve({ id: WS_ID }) };

describe("workspace/queue interlock", () => {
  const savedEnv = { ...process.env };
  beforeEach(() => {
    process.env.MICRO_EVAL_SERVER_MODE = "true";
    process.env.MICRO_EVAL_DATA_ROOT = "/tmp/root";
    queryQueueMock.mockReset();
    execFileSyncMock.mockReset();
    metaStatus = "active";
  });
  afterEach(() => {
    process.env = { ...savedEnv };
  });

  it("refuses to archive a workspace with pending jobs", async () => {
    queryQueueMock.mockReturnValue(true);
    const res = await PATCH(jsonRequest("PATCH", { status: "archived" }), ctx);
    expect(res.status).toBe(409);
    expect(execFileSyncMock).not.toHaveBeenCalled();
  });

  it("archives when nothing is pending", async () => {
    queryQueueMock.mockReturnValue(false);
    execFileSyncMock.mockReturnValue(JSON.stringify({ workspace_id: WS_ID, status: "archived" }));
    const res = await PATCH(jsonRequest("PATCH", { status: "archived" }), ctx);
    expect(res.status).toBe(200);
  });

  it("archives when queue.db does not exist yet (no jobs ever enqueued)", async () => {
    queryQueueMock.mockImplementation(() => {
      throw new Error("unable to open database file");
    });
    execFileSyncMock.mockReturnValue(JSON.stringify({ workspace_id: WS_ID, status: "archived" }));
    const res = await PATCH(jsonRequest("PATCH", { status: "archived" }), ctx);
    expect(res.status).toBe(200);
  });

  // R4 (round-6 review): any queue-check failure other than the expected
  // "queue.db doesn't exist yet" must fail closed — an unreadable queue
  // could be hiding pending jobs, so refuse the archive rather than
  // silently proceeding.
  it("refuses to archive when the queue check fails for an unexpected reason", async () => {
    queryQueueMock.mockImplementation(() => {
      throw new Error("database disk image is malformed");
    });
    const res = await PATCH(jsonRequest("PATCH", { status: "archived" }), ctx);
    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body.error).toBe("queue check failed");
    expect(execFileSyncMock).not.toHaveBeenCalled();
  });

  // Round-10 review: archived workspaces are read-only for config writes too.
  it("refuses configuration writes into an archived workspace", async () => {
    metaStatus = "archived";
    const res = await putConfiguration(
      jsonRequest("PUT", { id: "cfg", name: "cfg", agent: { name: "a", command: ["cat"] } }),
      ctx,
    );
    expect(res.status).toBe(409);
    expect((await res.json()).error).toContain("read-only");
    expect(execFileSyncMock).not.toHaveBeenCalled();
  });

  it("passes the member to the config CLI as --member for audit", async () => {
    execFileSyncMock.mockReturnValue(
      JSON.stringify({ schema_version: "1.0", project_name: "x", configurations: [], configuration_errors: [], tasks: [], warnings: [] }),
    );
    const res = await putConfiguration(
      jsonRequest("PUT", { id: "cfg", name: "cfg", agent: { name: "a", command: ["cat"] } }),
      ctx,
    );
    expect(res.status).toBe(200);
    const args = execFileSyncMock.mock.calls[0][1] as string[];
    expect(args.slice(0, 3)).toEqual(["run", "micro-eval", "config"]);
    expect(args).toContain("--member");
    expect(args[args.indexOf("--member") + 1]).toBe("alice");
  });

  it("refuses to enqueue into an archived workspace", async () => {
    metaStatus = "archived";
    const res = await enqueue(jsonRequest("POST"), ctx);
    expect(res.status).toBe(409);
    expect(execFileSyncMock).not.toHaveBeenCalled();
  });

  // Round-7 review: enqueue is one `workspace enqueue` CLI call that builds
  // the plan, compares the previewed digest and inserts the job under the
  // workspace + config locks. The route only maps its JSON refusals.
  const DIGEST = "a".repeat(64);

  function cliRefusal(payload: Record<string, unknown>, status = 1): never {
    const failure = new Error("Command failed") as Error & { status: number; stderr: string };
    failure.status = status;
    failure.stderr = `warning: something\n${JSON.stringify(payload)}\n`;
    throw failure;
  }

  it("enqueues through the locked CLI, passing owner and expected digest as argv", async () => {
    execFileSyncMock.mockReturnValue(JSON.stringify({ job_id: "job-1", status: "queued", position: 1, plan_digest: DIGEST }));
    const res = await enqueue(jsonRequest("POST", { expected_plan_digest: DIGEST }), ctx);
    expect(res.status).toBe(202);
    expect((await res.json()).job_id).toBe("job-1");
    const args = execFileSyncMock.mock.calls[0][1] as string[];
    expect(args.slice(0, 5)).toEqual(["run", "micro-eval", "workspace", "enqueue", WS_ID]);
    expect(args).toContain("--owner");
    expect(args).toContain("alice");
    expect(args.slice(-2)).toEqual(["--expected-plan-digest", DIGEST]);
    expect(execFileSyncMock.mock.calls[0][2]).not.toHaveProperty("shell");
  });

  it("enqueues without a digest when the body has none", async () => {
    execFileSyncMock.mockReturnValue(JSON.stringify({ job_id: "job-2", plan_digest: DIGEST }));
    const res = await enqueue(jsonRequest("POST"), ctx);
    expect(res.status).toBe(202);
    const args = execFileSyncMock.mock.calls[0][1] as string[];
    expect(args).not.toContain("--expected-plan-digest");
  });

  it.each([{}, { max_concurrency: 2 }, null])(
    "rejects config_overrides (%j) instead of silently ignoring it",
    async (config_overrides) => {
      const res = await enqueue(jsonRequest("POST", { config_overrides }), ctx);
      expect(res.status).toBe(400);
      expect((await res.json()).error).toBe("config_overrides is not supported");
      expect(execFileSyncMock).not.toHaveBeenCalled();
    },
  );

  it("rejects a malformed expected_plan_digest before touching the CLI", async () => {
    const res = await enqueue(jsonRequest("POST", { expected_plan_digest: "../x; --data-root /elsewhere" }), ctx);
    expect(res.status).toBe(400);
    expect(execFileSyncMock).not.toHaveBeenCalled();
  });

  it("maps plan_changed to 409 so the client refreshes its preview", async () => {
    execFileSyncMock.mockImplementation(() => cliRefusal({ error: "plan_changed", plan_digest: "b".repeat(64) }, 5));
    const res = await enqueue(jsonRequest("POST", { expected_plan_digest: DIGEST }), ctx);
    expect(res.status).toBe(409);
    const body = await res.json();
    expect(body.error).toContain("changed since the preview");
    expect(body.plan_digest).toBe("b".repeat(64));
  });

  it("maps queue_full to 429", async () => {
    execFileSyncMock.mockImplementation(() => cliRefusal({ error: "queue_full", current: 100, maximum: 100 }, 2));
    const res = await enqueue(jsonRequest("POST"), ctx);
    expect(res.status).toBe(429);
    expect((await res.json()).maximum).toBe(100);
  });

  it("maps a locked workspace_not_active refusal to 409", async () => {
    execFileSyncMock.mockImplementation(() => cliRefusal({ error: "workspace_not_active", status: "archived" }, 3));
    const res = await enqueue(jsonRequest("POST"), ctx);
    expect(res.status).toBe(409);
    expect((await res.json()).error).toContain("archived");
  });

  it("maps plan_build_failed to 502 with a sanitized detail", async () => {
    execFileSyncMock.mockImplementation(() =>
      cliRefusal({ error: "plan_build_failed", detail: "Task file must not be a symlink: t.yaml" }, 4),
    );
    const res = await enqueue(jsonRequest("POST"), ctx);
    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body.error).toBe("failed to build run plan");
    expect(body.detail).toContain("symlink");
  });

  it("attaches the fixed invalid-git-ref reason and hint, ignoring any CLI hint", async () => {
    execFileSyncMock.mockImplementation(() =>
      cliRefusal(
        {
          error: "plan_build_failed",
          detail: "[task=t] git ref cannot be resolved to a commit",
          reason: "invalid_git_ref",
          // A backend-supplied hint must never be forwarded verbatim; the
          // route only ever echoes its own constant for the known reason.
          hint: "arbitrary backend hint with /etc/passwd path",
        },
        4,
      ),
    );
    const res = await enqueue(jsonRequest("POST"), ctx);
    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body.reason).toBe("invalid_git_ref");
    expect(body.hint).toBe(
      "Use a branch, tag, or commit SHA that exists in the server repository and resolves to a commit. Correct the ref or fetch the required commit, then preview again.",
    );
    expect(body.hint).not.toContain("/etc/passwd");
  });

  it("does not attach a hint to a plan_build_failed refusal without the known reason", async () => {
    execFileSyncMock.mockImplementation(() =>
      cliRefusal({ error: "plan_build_failed", detail: "no tasks found" }, 4),
    );
    const res = await enqueue(jsonRequest("POST"), ctx);
    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body.reason).toBeUndefined();
    expect(body.hint).toBeUndefined();
  });

  // The CLI re-checks pending jobs under the workspace lock; when a job was
  // admitted between the route's pre-check and the CLI call, the refusal
  // must surface as 409, not as a generic 502.
  it("maps a locked CLI refusal (pending jobs) to 409 on archive", async () => {
    queryQueueMock.mockReturnValue(false);
    execFileSyncMock.mockImplementation(() => {
      const failure = new Error("Command failed") as Error & { status: number; stderr: string };
      failure.status = 1;
      failure.stderr = "Error: workspace has pending jobs; cancel them before archiving\n";
      throw failure;
    });
    const res = await PATCH(jsonRequest("PATCH", { status: "archived" }), ctx);
    expect(res.status).toBe(409);
    expect((await res.json()).error).toContain("pending");
  });

  it("refuses to delete a workspace with pending jobs", async () => {
    queryQueueMock.mockReturnValue(true);
    const res = await DELETE(jsonRequest("DELETE"), ctx);
    expect(res.status).toBe(409);
    expect(execFileSyncMock).not.toHaveBeenCalled();
  });

  it("refuses to delete when the queue check fails for an unexpected reason", async () => {
    queryQueueMock.mockImplementation(() => {
      throw new Error("database is locked");
    });
    const res = await DELETE(jsonRequest("DELETE"), ctx);
    expect(res.status).toBe(502);
    expect((await res.json()).error).toBe("queue check failed");
    expect(execFileSyncMock).not.toHaveBeenCalled();
  });

  it("deletes when queue.db does not exist yet", async () => {
    queryQueueMock.mockImplementation(() => {
      throw new Error("unable to open database file");
    });
    execFileSyncMock.mockReturnValue("");
    const res = await DELETE(jsonRequest("DELETE"), ctx);
    expect(res.status).toBe(200);
    expect((await res.json()).deleted).toBe(true);
  });

  it("maps a locked CLI refusal (pending jobs) to 409 on delete", async () => {
    queryQueueMock.mockReturnValue(false);
    execFileSyncMock.mockImplementation(() => {
      const failure = new Error("Command failed") as Error & { status: number; stderr: string };
      failure.status = 1;
      failure.stderr = "Error: workspace has pending jobs; cancel them before deleting\n";
      throw failure;
    });
    const res = await DELETE(jsonRequest("DELETE"), ctx);
    expect(res.status).toBe(409);
  });
});

describe("plan-summary redaction", () => {
  const savedEnv = { ...process.env };
  beforeEach(() => {
    process.env.MICRO_EVAL_SERVER_MODE = "true";
    process.env.MICRO_EVAL_SECRET_API_KEY = "sk-live-secret-value-123456";
    execFileSyncMock.mockReset();
  });
  afterEach(() => {
    process.env = { ...savedEnv };
  });

  it("masks declared secret values inside agent commands", async () => {
    execFileSyncMock.mockReturnValue(
      JSON.stringify({
        plan_digest: "c".repeat(64),
        plan: {
          cells: [
            {
              task: { id: "t" },
              configuration: { id: "c", agent: { command: ["curl", "-H", "Bearer sk-live-secret-value-123456"] } },
              repetition: 1,
            },
          ],
        },
      }),
    );
    const res = await planSummary(new Request(`http://localhost/api/workspaces/${WS_ID}/plan-summary`), ctx);
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.agent_commands[0]).toContain("[REDACTED:MICRO_EVAL_SECRET_API_KEY]");
    expect(JSON.stringify(body)).not.toContain("sk-live-secret-value-123456");
    expect(body.plan_digest).toBe("c".repeat(64));
    // Preview goes through the same CLI path as admission (round-8 review).
    const args = execFileSyncMock.mock.calls[0][1] as string[];
    expect(args.slice(0, 6)).toEqual(["run", "micro-eval", "workspace", "enqueue", WS_ID, "--dry-run"]);
  });

  it("maps a plan_build_failed refusal to 502 with the CLI detail", async () => {
    execFileSyncMock.mockImplementation(() => {
      const failure = new Error("Command failed") as Error & { status: number; stderr: string };
      failure.status = 4;
      failure.stderr = JSON.stringify({ error: "plan_build_failed", detail: "output_dir must be .micro-eval/runs on the Team Server" }) + "\n";
      throw failure;
    });
    const res = await planSummary(new Request(`http://localhost/api/workspaces/${WS_ID}/plan-summary`), ctx);
    expect(res.status).toBe(502);
    expect((await res.json()).detail).toContain("output_dir");
  });

  it("attaches the fixed invalid-git-ref reason and hint on a refusal", async () => {
    execFileSyncMock.mockImplementation(() => {
      const failure = new Error("Command failed") as Error & { status: number; stderr: string };
      failure.status = 4;
      failure.stderr =
        JSON.stringify({
          error: "plan_build_failed",
          detail: "[task=t] git ref cannot be resolved to a commit",
          reason: "invalid_git_ref",
        }) + "\n";
      throw failure;
    });
    const res = await planSummary(new Request(`http://localhost/api/workspaces/${WS_ID}/plan-summary`), ctx);
    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body.reason).toBe("invalid_git_ref");
    expect(body.hint).toContain("then preview again");
  });
});
