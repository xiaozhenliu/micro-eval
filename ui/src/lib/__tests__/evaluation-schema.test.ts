/**
 * Cross-language validation parity for EvaluationResult (issue #6).
 *
 * Python EvaluationResult enforces, via a model validator, that a pass/fail
 * verdict must carry at least one evidence reference
 * (test_pass_fail_evaluation_requires_evidence_refs in
 * tests/unit/test_canonical_models.py). The zod schema previously only mirrored
 * the pass_fail enum, not this cross-field rule, so the UI would silently accept
 * an evidence-less pass/fail evaluation that the Python side rejects.
 */

import { describe, it, expect } from "vitest";
import { EvaluationResultSchema } from "../schema";

const base = {
  evaluation_id: "e1",
  cell_id: "c1",
  evaluator: "human",
};

describe("EvaluationResult: pass_fail requires evidence_refs (#6)", () => {
  it("rejects a pass verdict with no evidence_refs (mirrors Python)", () => {
    const result = EvaluationResultSchema.safeParse({ ...base, pass_fail: "pass" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((issue) => issue.path.includes("evidence_refs"))).toBe(true);
    }
  });

  it("rejects a fail verdict with empty evidence_refs", () => {
    const result = EvaluationResultSchema.safeParse({ ...base, pass_fail: "fail", evidence_refs: [] });
    expect(result.success).toBe(false);
  });

  it("accepts a pass verdict backed by evidence_refs", () => {
    const result = EvaluationResultSchema.safeParse({
      ...base,
      pass_fail: "pass",
      evidence_refs: ["c1::evidence::process"],
    });
    expect(result.success).toBe(true);
  });

  it("accepts a null verdict with no evidence_refs", () => {
    const result = EvaluationResultSchema.safeParse({ ...base, pass_fail: null });
    expect(result.success).toBe(true);
  });
});
