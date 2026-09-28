// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const queryQueueMock = vi.fn();
const readWorkspaceMetaMock = vi.fn();

vi.mock("@/lib/server-validation", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/server-validation")>();
  return { ...actual, queryQueue: (...args: unknown[]) => queryQueueMock(...args) };
});
vi.mock("@/lib/workspace-api", () => ({
  readWorkspaceMeta: (...args: unknown[]) => readWorkspaceMetaMock(...args),
}));

import { GET } from "@/app/api/workspaces/[id]/jobs/[jobId]/route";

const JOB_ID = "job-20260912T095224Z-f338f30f";
const WORKSPACE_ID = "ws-20260912T095109Z-dd4c3ea3";
const OTHER_WORKSPACE_ID = "ws-20260912T095109Z-aaaaaaaa";

function request(workspaceId = WORKSPACE_ID, jobId = JOB_ID) {
  return GET(
    new Request(`http://localhost/api/workspaces/${workspaceId}/jobs/${jobId}`),
    { params: Promise.resolve({ id: workspaceId, jobId }) },
  );
}

describe("workspace-scoped job lookup", () => {
  const savedEnv = { ...process.env };

  beforeEach(() => {
    process.env.MICRO_EVAL_SERVER_MODE = "true";
    queryQueueMock.mockReset();
    readWorkspaceMetaMock.mockReset();
    readWorkspaceMetaMock.mockReturnValue({ workspace_id: WORKSPACE_ID });
  });
  afterEach(() => {
    process.env = { ...savedEnv };
  });

  it("returns only a job belonging to the requested workspace and omits its RunPlan", async () => {
    queryQueueMock.mockReturnValue({
      job_id: JOB_ID,
      workspace_id: WORKSPACE_ID,
      status: "running",
      progress: { completed_cells: 1, total_cells: 2 },
      plan_json: '{"agent":{"env":{"TOKEN":"secret"}}}',
    });

    const response = await request();
    expect(response.status).toBe(200);
    const job = await response.json();
    expect(job.workspace_id).toBe(WORKSPACE_ID);
    expect(job.progress.completed_cells).toBe(1);
    expect(job).not.toHaveProperty("plan_json");
    expect(JSON.stringify(job)).not.toContain("secret");
  });

  it("returns 404 for a job owned by another workspace", async () => {
    queryQueueMock.mockReturnValue({ job_id: JOB_ID, workspace_id: OTHER_WORKSPACE_ID });
    const response = await request();
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "job not found" });
  });

  it("returns 404 for a nonexistent workspace before querying the job", async () => {
    readWorkspaceMetaMock.mockReturnValue(null);
    const response = await request();
    expect(response.status).toBe(404);
    expect(queryQueueMock).not.toHaveBeenCalled();
  });

  it("rejects an invalid job id", async () => {
    const response = await request(WORKSPACE_ID, "bad-id");
    expect(response.status).toBe(400);
    expect(queryQueueMock).not.toHaveBeenCalled();
  });
});
