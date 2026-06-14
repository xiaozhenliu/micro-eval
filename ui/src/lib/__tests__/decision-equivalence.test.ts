/**
 * Cross-language decision-algorithm equivalence contract (issue #1).
 *
 * The UI `recomputeDecision` (evaluation.ts) hand-mirrors the Python
 * `build_decision` algorithm. The schema golden only guards shape, not
 * algorithmic equivalence, so the two implementations could silently drift
 * (e.g. cost aggregation, caveat ordering, pass@k formulas).
 *
 * This test feeds the canonical input run from
 * tests/contract/golden/decision-equivalence.json (whose `expected_decision`
 * is produced by the *Python* algorithm) into `recomputeDecision` and asserts
 * the result matches. Time-dependent fields are stripped and numbers are
 * compared with a small tolerance to absorb cross-language float noise.
 */

import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { RunSchema } from "../schema";
import { recomputeDecision } from "../evaluation";

const GOLDEN_PATH = path.resolve(
  __dirname,
  "../../../../tests/contract/golden/decision-equivalence.json",
);

const TIME_FIELDS = ["decision_report_id", "timestamp", "created_at"];
const FLOAT_TOLERANCE = 1e-9;

function stripTimeFields(decision: Record<string, unknown>): Record<string, unknown> {
  const out = { ...decision };
  for (const field of TIME_FIELDS) delete out[field];
  return out;
}

/**
 * Recursive structural equality with a numeric tolerance. The Python golden
 * stores rounded floats; the TS recompute produces full-precision floats, so an
 * exact toEqual would be fragile across languages.
 */
function assertDeepEqualWithTolerance(actual: unknown, expected: unknown, where: string): void {
  if (typeof expected === "number" && typeof actual === "number") {
    expect(Math.abs(actual - expected), `${where}: ${actual} != ${expected}`).toBeLessThanOrEqual(
      FLOAT_TOLERANCE,
    );
    return;
  }
  if (Array.isArray(expected)) {
    expect(Array.isArray(actual), `${where}: expected array`).toBe(true);
    const actualArr = actual as unknown[];
    expect(actualArr.length, `${where}: array length`).toBe(expected.length);
    expected.forEach((item, index) =>
      assertDeepEqualWithTolerance(actualArr[index], item, `${where}[${index}]`),
    );
    return;
  }
  if (expected !== null && typeof expected === "object") {
    expect(actual !== null && typeof actual === "object", `${where}: expected object`).toBe(true);
    const expectedObj = expected as Record<string, unknown>;
    const actualObj = actual as Record<string, unknown>;
    expect(new Set(Object.keys(actualObj)), `${where}: key set`).toEqual(
      new Set(Object.keys(expectedObj)),
    );
    for (const key of Object.keys(expectedObj)) {
      assertDeepEqualWithTolerance(actualObj[key], expectedObj[key], `${where}.${key}`);
    }
    return;
  }
  expect(actual, where).toBe(expected);
}

describe("decision algorithm equivalence: recomputeDecision vs Python build_decision", () => {
  const golden = JSON.parse(fs.readFileSync(GOLDEN_PATH, "utf-8")) as {
    run: unknown;
    expected_decision: Record<string, unknown>;
  };

  it("input run parses against the zod Run schema", () => {
    expect(() => RunSchema.parse(golden.run)).not.toThrow();
  });

  it("produces a decision identical to the Python algorithm (caveats, aggregation, cost)", () => {
    const run = RunSchema.parse(golden.run);
    const decision = recomputeDecision(run);
    expect(decision).not.toBeNull();
    const normalized = stripTimeFields(decision as unknown as Record<string, unknown>);
    assertDeepEqualWithTolerance(normalized, golden.expected_decision, "decision");
  });

  it("aggregates trace cost per configuration (regression guard for the wiped-cost bug)", () => {
    const run = RunSchema.parse(golden.run);
    const decision = recomputeDecision(run);
    const baseline = decision?.aggregation.per_configuration["baseline"];
    // baseline has two cost-bearing traces (0.01 + 0.02) plus one null-cost trace.
    expect(baseline?.total_cost?.amount).toBeCloseTo(0.03, 9);
    expect(baseline?.total_cost?.source).toBe("langfuse");
  });
});
