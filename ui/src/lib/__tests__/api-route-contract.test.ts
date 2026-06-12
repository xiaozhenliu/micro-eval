/**
 * ISSUE-1: UI API route cross-language contract integration tests.
 *
 * Validates that Python-produced run fixtures (canonical-run-phase2.json) are
 * correctly consumed by lib/api.ts helper functions and pass zod schema strict
 * parsing — the boundary between Pydantic (Python write) and zod (TS read).
 *
 * Tests must be deterministic and have zero network dependency.
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { RunSchema, DecisionReportSchema, TraceRefSchema } from "../schema";

// Load shared fixture produced by Python Pydantic model_dump_json().
const FIXTURE_DIR = path.resolve(__dirname, "../fixtures");
const phase2RunRaw: unknown = JSON.parse(
  fs.readFileSync(path.join(FIXTURE_DIR, "canonical-run-phase2.json"), "utf-8")
);
const phase2DecisionRaw: unknown = JSON.parse(
  fs.readFileSync(path.join(FIXTURE_DIR, "canonical-decision-phase2.json"), "utf-8")
);

// ----------------------------------------------------------------------------
// RunSchema strict parsing
// ----------------------------------------------------------------------------

describe("ISSUE-1: RunSchema parses Phase 2 Pydantic fixture strictly", () => {
  it("parses run.json produced by Pydantic model_dump_json without error", () => {
    expect(() => RunSchema.parse(phase2RunRaw)).not.toThrow();
  });

  it("run has decision field populated", () => {
    const run = RunSchema.parse(phase2RunRaw);
    expect(run.decision).not.toBeNull();
    expect(run.decision?.decision_report_id).toBe(
      "run-phase2-fixture::decision::20260612T000000Z"
    );
  });

  it("run has TraceRef entries with provider and cost fields", () => {
    const run = RunSchema.parse(phase2RunRaw);
    expect(run.traces.length).toBeGreaterThan(0);
    const trace = run.traces[0];
    expect(trace.provider).toBe("process");
    // cost is a CostMetric; source field must exist
    expect(trace.cost?.source).toBe("unavailable");
  });

  it("run has llm_judge evaluation entries", () => {
    const run = RunSchema.parse(phase2RunRaw);
    const judgeEvals = run.evaluations.filter((e) => e.evaluator_type === "llm_judge");
    expect(judgeEvals.length).toBeGreaterThan(0);
    // rubric_hash is a Phase 2 field; must survive round-trip
    expect(judgeEvals[0].rubric_hash).toBeTruthy();
  });

  it("per_configuration stats have pass_at_k (Phase 2 field)", () => {
    const run = RunSchema.parse(phase2RunRaw);
    const aggregation = run.decision?.aggregation;
    expect(aggregation).toBeDefined();
    const baseline = aggregation?.per_configuration["baseline"];
    expect(baseline?.pass_at_k).toBeDefined();
    expect(Object.keys(baseline?.pass_at_k ?? {}).length).toBeGreaterThan(0);
  });
});

// ----------------------------------------------------------------------------
// DecisionReportSchema strict parsing (decision.json standalone)
// ----------------------------------------------------------------------------

describe("ISSUE-1: DecisionReportSchema parses standalone decision.json", () => {
  it("parses decision.json produced by Python without error", () => {
    expect(() => DecisionReportSchema.parse(phase2DecisionRaw)).not.toThrow();
  });

  it("decision_report_id is present and non-empty", () => {
    const decision = DecisionReportSchema.parse(phase2DecisionRaw);
    expect(decision.decision_report_id).toBeTruthy();
  });

  it("verdict is a valid enum value", () => {
    const decision = DecisionReportSchema.parse(phase2DecisionRaw);
    const validVerdicts = ["improved", "regressed", "mixed", "inconclusive", "not_comparable", "needs_human_review"];
    expect(validVerdicts).toContain(decision.verdict);
  });
});

// ----------------------------------------------------------------------------
// lib/api.ts getRun / getCellTrace simulate reading from .micro-eval directory
// ----------------------------------------------------------------------------

describe("ISSUE-1: lib/api.ts functions consume Phase 2 fixture directory", () => {
  let tmpDir: string;

  beforeEach(() => {
    // Build a minimal .micro-eval/runs/<id>/ directory that mirrors real output
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "micro-eval-test-"));
    const runId = "run-phase2-fixture";
    const runDir = path.join(tmpDir, ".micro-eval", "runs", runId);
    fs.mkdirSync(runDir, { recursive: true });

    // Write run.json (fixture without decision field so getRun reads decision.json)
    const runData = { ...(phase2RunRaw as Record<string, unknown>), decision: null };
    fs.writeFileSync(path.join(runDir, "run.json"), JSON.stringify(runData));

    // Write decision.json separately (Phase 2 pattern)
    fs.writeFileSync(
      path.join(runDir, "decision.json"),
      JSON.stringify(phase2DecisionRaw)
    );
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it("getRun merges decision.json into run when run.json has no decision", async () => {
    // Set env var so lib/api.ts resolves to our tmp directory
    process.env.MICRO_EVAL_PROJECT_ROOT = tmpDir;
    try {
      const { getRun } = await import("../api");
      const run = await getRun("run-phase2-fixture");
      expect(run).not.toBeNull();
      expect(run?.decision).not.toBeNull();
      expect(run?.decision?.decision_report_id).toBeTruthy();
    } finally {
      delete process.env.MICRO_EVAL_PROJECT_ROOT;
    }
  });

  it("getCellTrace returns TraceRef array that passes zod parsing for known cell", async () => {
    process.env.MICRO_EVAL_PROJECT_ROOT = tmpDir;
    try {
      const { getCellTrace } = await import("../api");
      const traces = await getCellTrace("run-phase2-fixture", "cell-b1");
      expect(Array.isArray(traces)).toBe(true);
      // Validate each trace against zod schema
      for (const trace of traces) {
        expect(() => TraceRefSchema.parse(trace)).not.toThrow();
      }
    } finally {
      delete process.env.MICRO_EVAL_PROJECT_ROOT;
    }
  });
});
