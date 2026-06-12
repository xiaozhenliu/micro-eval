import { describe, it, expect } from "vitest";
import { recomputeDecision } from "../evaluation";
import type { Run } from "../schema";

// Minimal valid Run for testing denominator_policy propagation.
function makeRun(overrides: Partial<Run> = {}): Run {
  return {
    schema_version: "1.0",
    id: "run-test",
    project_name: "test",
    status: "completed",
    created_at: "2026-06-12T00:00:00Z",
    completed_at: null,
    output_dir: ".micro-eval/runs",
    config_hash: "",
    tasks: ["task-a"],
    configurations: ["cfg-a"],
    cells: [],
    results: [],
    migration_warnings: [],
    same_start_snapshot: null,
    replay_canonical: null,
    artifacts: [],
    evidence: [],
    traces: [],
    evaluations: [],
    decision: null,
    denominator_policy: "include_failed",
    ...overrides,
  };
}

function cellResult(cellId: string, status: "pass" | "fail" | "error" | "timeout", passFail: "pass" | "fail" | null) {
  return {
    schema_version: "1.0",
    cell_id: cellId,
    run_id: "run-test",
    task_id: "task-a",
    configuration_id: "cfg-a",
    configuration_name: "cfg-a",
    repetition: 1,
    status,
    score: null,
    pass_fail: passFail,
    output_summary: "",
    stdout_summary: "",
    stderr_summary: "",
    exit_code: null,
    latency_s: 1.0,
    failure_mode: null,
    artifact_refs: [],
    evidence_refs: [],
    evaluation_refs: [],
    trace_refs: [],
    cell_snapshot: null,
    snapshot_gate_result: null,
  };
}

describe("recomputeDecision denominator_policy", () => {
  it("include_failed counts all cells in the denominator", () => {
    const run = makeRun({
      denominator_policy: "include_failed",
      results: [
        cellResult("c1", "pass", "pass"),
        cellResult("c2", "error", null),
        cellResult("c3", "pass", "pass"),
        cellResult("c4", "pass", "pass"),
      ],
    });
    const decision = recomputeDecision(run)!;
    const stats = decision.aggregation.per_configuration["cfg-a"];
    // 3 passed / 4 total = 0.75
    expect(stats.pass_rate).toBeCloseTo(0.75);
    expect(stats.denominator_policy).toBe("include_failed");
  });

  it("exclude_failed excludes error/timeout cells from the denominator", () => {
    const run = makeRun({
      denominator_policy: "exclude_failed",
      results: [
        cellResult("c1", "pass", "pass"),
        cellResult("c2", "error", null),
        cellResult("c3", "pass", "pass"),
        cellResult("c4", "pass", "pass"),
      ],
    });
    const decision = recomputeDecision(run)!;
    const stats = decision.aggregation.per_configuration["cfg-a"];
    // 3 passed / 3 successful (error excluded) = 1.0
    expect(stats.pass_rate).toBeCloseTo(1.0);
    expect(stats.denominator_policy).toBe("exclude_failed");
  });

  it("exclude_failed partial pass reflects correct rate", () => {
    const run = makeRun({
      denominator_policy: "exclude_failed",
      results: [
        cellResult("c1", "pass", "pass"),
        cellResult("c2", "fail", "fail"),
        cellResult("c3", "error", null),
      ],
    });
    const decision = recomputeDecision(run)!;
    const stats = decision.aggregation.per_configuration["cfg-a"];
    // 1 passed / 2 successful = 0.5
    expect(stats.pass_rate).toBeCloseTo(0.5);
    expect(stats.denominator_policy).toBe("exclude_failed");
  });
});
