import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { JobSchema } from "@/lib/schema";
import { QueueJobCard } from "../QueueJobCard";

function job(overrides: Record<string, unknown> = {}) {
  return JobSchema.parse({
    job_id: "job-20260912T095224Z-f338f30f",
    workspace_id: "ws-20260912T095109Z-dd4c3ea3",
    owner: "alice",
    status: "running",
    enqueued_at: "2026-09-12T09:52:24Z",
    ...overrides,
  });
}

describe("QueueJobCard", () => {
  it("renders dashboard progress from completed and total cell counts", () => {
    const html = renderToStaticMarkup(
      <QueueJobCard job={job({ progress: { completed_cells: 3, total_cells: 12 } })} />,
    );
    expect(html).toContain("25%");
    expect(html).toContain("width:25%");
    expect(html).not.toContain("NaN");
  });

  it("handles a zero-cell progress record without NaN", () => {
    const html = renderToStaticMarkup(
      <QueueJobCard job={job({ progress: { completed_cells: 0, total_cells: 0 } })} />,
    );
    expect(html).toContain("0%");
    expect(html).not.toContain("NaN");
  });

  it("recognizes the worker's done status and rejects string progress", () => {
    const html = renderToStaticMarkup(<QueueJobCard job={job({ status: "done" })} />);
    expect(html).toContain(">done<");
    expect(JobSchema.safeParse({ ...job(), progress: '{"completed_cells":1}' }).success).toBe(false);
  });
});
