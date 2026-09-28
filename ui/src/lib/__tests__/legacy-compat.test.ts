/**
 * ISSUE-3: Legacy v0.1.x run.json zod compatibility test.
 *
 * Verifies that zod RunSchema can parse the same fixture used by Python-side
 * ISSUE-3 tests — decision embedded in run.json, no Phase 2 fields.
 */

import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { RunSchema } from "../schema";

const GOLDEN_DIR = path.resolve(__dirname, "../../../../tests/contract/golden");
const legacyRaw: unknown = JSON.parse(
  fs.readFileSync(path.join(GOLDEN_DIR, "run-legacy-v01x.json"), "utf-8")
);

describe("ISSUE-3: zod RunSchema parses legacy v0.1.x fixture", () => {
  it("parses without throwing", () => {
    expect(() => RunSchema.parse(legacyRaw)).not.toThrow();
  });

  it("decision verdict is read from embedded run.json decision", () => {
    const run = RunSchema.parse(legacyRaw);
    expect(run.decision?.verdict).toBe("regressed");
  });

  it("legacy aggregation stats migrate to ConfigurationStats shape", () => {
    const run = RunSchema.parse(legacyRaw);
    const baseline = run.decision?.aggregation.per_configuration["baseline"];
    expect(baseline).toBeDefined();
    // pass_rate must be populated (migrated from old stats.passed/total)
    expect(baseline?.pass_rate).toBe(1.0);
  });
});
