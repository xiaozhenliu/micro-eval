// @vitest-environment node
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const paths = vi.hoisted(() => ({ runsDir: "" }));

vi.mock("@/lib/server-mode", () => ({ isServerMode: () => true }));
vi.mock("@/lib/workspace-api", () => ({
  getWorkspaceRunsDir: () => paths.runsDir,
  resolveWorkspaceRunDir: (_workspaceId: string, runId: string) => path.join(paths.runsDir, runId),
  resolveInsideRunDir: (runDir: string, fileName: string) => path.join(runDir, fileName),
}));

import { GET as getRun } from "@/app/api/workspaces/[id]/runs/[runId]/route";
import { GET as listRuns } from "@/app/api/workspaces/[id]/runs/route";

const RUN_ID = "run-phase2-fixture";
const WORKSPACE_ID = "ws-test";
const GOLDEN_RUN = path.resolve(__dirname, "../../../tests/contract/golden/run-phase2-full.json");

describe("cancelled workspace run read routes", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "micro-eval-cancelled-run-"));
    paths.runsDir = tmpDir;
    const runDir = path.join(tmpDir, RUN_ID);
    fs.mkdirSync(runDir);
    const raw = JSON.parse(fs.readFileSync(GOLDEN_RUN, "utf-8"));
    raw.status = "cancelled";
    raw.results = raw.results.slice(0, 1);
    raw.decision.verdict = "inconclusive";
    fs.writeFileSync(path.join(runDir, "run.json"), JSON.stringify(raw));
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
    paths.runsDir = "";
  });

  it("serves the retained cell result from the run detail route", async () => {
    const response = await getRun(
      new Request(`http://localhost/api/workspaces/${WORKSPACE_ID}/runs/${RUN_ID}`),
      { params: Promise.resolve({ id: WORKSPACE_ID, runId: RUN_ID }) },
    );

    expect(response.status).toBe(200);
    const run = await response.json();
    expect(run.status).toBe("cancelled");
    expect(run.results).toHaveLength(1);
    expect(run.results[0].cell_id).toBeTruthy();
    expect(run.decision.verdict).toBe("inconclusive");
  });

  it("keeps the cancelled partial run in the workspace run list", async () => {
    const response = await listRuns(
      new Request(`http://localhost/api/workspaces/${WORKSPACE_ID}/runs`),
      { params: Promise.resolve({ id: WORKSPACE_ID }) },
    );

    expect(response.status).toBe(200);
    const runs = await response.json();
    expect(runs).toHaveLength(1);
    expect(runs[0].status).toBe("cancelled");
    expect(runs[0].results).toHaveLength(1);
  });
});
