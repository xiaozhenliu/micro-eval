// @vitest-environment node
/**
 * Round-4 review: queue job rows embed the full RunPlan (`plan_json`,
 * including agent.env). Neither GET /api/jobs/[jobId] nor GET /api/queue may
 * return it.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const queryQueueMock = vi.fn();
vi.mock("@/lib/server-validation", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/server-validation")>();
  return { ...actual, queryQueue: (...args: unknown[]) => queryQueueMock(...args) };
});

import { GET as getJob } from "@/app/api/jobs/[jobId]/route";
import { GET as getQueue } from "@/app/api/queue/route";

const JOB_ID = "job-20260912T095224Z-f338f30f";

function jobRow(status: string) {
  return {
    job_id: JOB_ID,
    workspace_id: "ws-20260912T095109Z-dd4c3ea3",
    owner: "xz",
    status,
    enqueued_at: "2026-09-12T09:52:24Z",
    plan_json: JSON.stringify({ cells: [{ configuration: { agent: { env: { TOKEN: "sk-live-secret" } } } }] }),
    progress: null,
  };
}

describe("queue responses never include plan_json", () => {
  const savedEnv = { ...process.env };
  beforeEach(() => {
    process.env.MICRO_EVAL_SERVER_MODE = "true";
    queryQueueMock.mockReset();
  });
  afterEach(() => {
    process.env = { ...savedEnv };
  });

  it("GET /api/jobs/[jobId] strips plan_json", async () => {
    queryQueueMock.mockReturnValue(jobRow("done"));
    const res = await getJob(new Request(`http://localhost/api/jobs/${JOB_ID}`), { params: Promise.resolve({ jobId: JOB_ID }) });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.job_id).toBe(JOB_ID);
    expect(body).not.toHaveProperty("plan_json");
    expect(JSON.stringify(body)).not.toContain("sk-live-secret");
  });

  it("GET /api/queue strips plan_json from every section", async () => {
    queryQueueMock.mockReturnValue({ running: jobRow("running"), queued: [jobRow("queued")], recent_completed: [jobRow("done")] });
    const res = await getQueue();
    expect(res.status).toBe(200);
    const text = JSON.stringify(await res.json());
    expect(text).not.toContain("plan_json");
    expect(text).not.toContain("sk-live-secret");
  });
});
