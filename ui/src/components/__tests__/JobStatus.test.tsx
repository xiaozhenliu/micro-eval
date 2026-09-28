/**
 * GRO-556: JobStatus is the landing view after "Enqueue Run". It must poll
 * the job endpoint, surface progress and errors, and hand the user over to
 * the run page once the job is done.
 */

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { JobStatus, type JobView } from "../JobStatus";

const replaceMock = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: replaceMock,
    refresh: vi.fn(),
  }),
}));

function jobFixture(overrides: Partial<JobView>): JobView {
  return {
    job_id: "job-20260912T095224Z-f338f30f",
    // Matches the `workspaceId="ws-1"` used by every render() call below so
    // the F13 workspace-mismatch check only fires when a test overrides it.
    workspace_id: "ws-1",
    owner: "xz",
    status: "queued",
    enqueued_at: "2026-09-12T09:52:24Z",
    started_at: null,
    finished_at: null,
    run_id: null,
    error: null,
    progress: null,
    cancel_requested_at: null,
    cancelled_by: null,
    ...overrides,
  };
}

function mockFetchJob(job: JobView) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => job,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("JobStatus", () => {
  afterEach(() => {
    cleanup();
    replaceMock.mockReset();
    vi.unstubAllGlobals();
  });

  it("links to the run and redirects when the job is done", async () => {
    const fetchMock = mockFetchJob(jobFixture({ status: "done", run_id: "run-20260912T095224Z-cd9c877d" }));

    render(<JobStatus workspaceId="ws-1" jobId="job-20260912T095224Z-f338f30f" pollIntervalMs={60_000} />);

    const link = await screen.findByRole("link", { name: "View run" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workspaces/ws-1/jobs/job-20260912T095224Z-f338f30f",
      { cache: "no-store" },
    );
    expect(link.getAttribute("href")).toBe("/workspace/ws-1/run/run-20260912T095224Z-cd9c877d");
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/workspace/ws-1/run/run-20260912T095224Z-cd9c877d"));
  });

  it("shows cell progress and a cancel button while running, without redirecting", async () => {
    mockFetchJob(
      jobFixture({
        status: "running",
        started_at: "2026-09-12T09:52:26Z",
        progress: { completed_cells: 1, total_cells: 2, current_task: "hello-echo", current_config: "echo-b" },
      }),
    );

    render(<JobStatus workspaceId="ws-1" jobId="job-20260912T095224Z-f338f30f" pollIntervalMs={60_000} />);

    expect(await screen.findByText(/1 \/ 2 cells/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cancel after active cells" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "View run" })).toBeNull();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("surfaces the worker error when the job failed", async () => {
    mockFetchJob(jobFixture({ status: "failed", error: "plan validation failed" }));

    render(<JobStatus workspaceId="ws-1" jobId="job-20260912T095224Z-f338f30f" pollIntervalMs={60_000} />);

    expect(await screen.findByText("plan validation failed")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Back to workspace" }).getAttribute("href")).toBe("/workspace/ws-1");
    expect(screen.queryByRole("button", { name: "Cancel" })).toBeNull();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("shows retained progress and a run link after cancellation", async () => {
    mockFetchJob(jobFixture({
      status: "cancelled",
      finished_at: "2026-09-12T09:52:27Z",
      run_id: "run-20260912T095224Z-cd9c877d",
      progress: { completed_cells: 1, total_cells: 3, current_task: "hello-echo", current_config: null },
    }));

    render(<JobStatus workspaceId="ws-1" jobId="job-20260912T095224Z-f338f30f" pollIntervalMs={60_000} />);

    expect(await screen.findByText("Cancelled — retained 1/3 cells.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "View run" }).getAttribute("href")).toBe("/workspace/ws-1/run/run-20260912T095224Z-cd9c877d");
    expect(screen.queryByRole("button", { name: "Cancel" })).toBeNull();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("explains the wait and prevents repeat cancellation while cells are active", async () => {
    mockFetchJob(jobFixture({
      status: "running",
      cancel_requested_at: "2026-09-12T09:52:26Z",
      progress: { completed_cells: 1, total_cells: 3, current_task: null, current_config: null },
    }));

    render(<JobStatus workspaceId="ws-1" jobId="job-20260912T095224Z-f338f30f" pollIntervalMs={60_000} />);

    expect(await screen.findByText("cancel requested — waiting for active cells")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Cancel/ })).toBeNull();
  });

  it("shows a mismatch warning and does not link or redirect when the job belongs to another workspace (F13)", async () => {
    mockFetchJob(
      jobFixture({
        workspace_id: "ws-other",
        status: "done",
        run_id: "run-20260912T095224Z-cd9c877d",
      }),
    );

    render(<JobStatus workspaceId="ws-1" jobId="job-20260912T095224Z-f338f30f" pollIntervalMs={60_000} />);

    expect(await screen.findByText("This job belongs to a different workspace.")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "View run" })).toBeNull();
    expect(replaceMock).not.toHaveBeenCalled();
  });
});
