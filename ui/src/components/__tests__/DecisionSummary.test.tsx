/**
 * ISSUE-5: Decision Surface honesty assertions.
 *
 * Two acceptance tests per Unicorn §5.8 obligations:
 * 1. not_comparable run must NOT display a winner marker.
 * 2. low_sample caveat must be visible in the rendered output.
 *
 * No snapshot tests — only targeted behavioral assertions.
 */

import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { DecisionSummary } from "../DecisionSummary";
import type { Run } from "@/lib/schema";

// Minimal Run factory — only fields consumed by DecisionSummary.
function makeRun(
  verdict: string,
  caveats: string[],
  perConfig: Record<
    string,
    { pass_rate: number; n_cells: number; mean_latency_ms: number; caveats: string[]; pass_at_k: Record<string, number> | null }
  >
): Run {
  return {
    schema_version: "1.0",
    id: "run-test",
    project_name: "test",
    status: "completed",
    created_at: "2026-06-12T00:00:00Z",
    completed_at: null,
    output_dir: ".micro-eval/runs",
    config_hash: "",
    tasks: [],
    configurations: [],
    cells: [],
    results: [],
    migration_warnings: [],
    same_start_snapshot: null,
    replay_canonical: null,
    artifacts: [],
    evidence: [],
    traces: [],
    evaluations: [],
    denominator_policy: "include_failed",
    decision: {
      schema_version: "1.0",
      decision_report_id: "run-test::decision::20260612T000000Z",
      verdict: verdict as NonNullable<Run["decision"]>["verdict"],
      confidence: "low",
      evaluation_refs: [],
      evidence_refs: [],
      caveats,
      aggregation: {
        schema_version: "1.0",
        per_configuration: Object.fromEntries(
          Object.entries(perConfig).map(([id, s]) => [
            id,
            {
              schema_version: "1.0",
              n_cells: s.n_cells,
              n_successful: s.n_cells,
              pass_rate: s.pass_rate,
              pass_at_k: s.pass_at_k ?? { "1": s.pass_rate },
              pass_hat_k: null,
              mean_latency_ms: s.mean_latency_ms,
              median_latency_ms: null,
              total_cost: null,
              denominator_policy: "include_failed" as const,
              caveats: s.caveats,
            },
          ])
        ),
      },
      recommended_action: "review evidence",
      timestamp: "20260612T000000Z",
      created_at: "20260612T000000Z",
    },
  };
}

describe("ISSUE-5: DecisionSummary honesty obligations", () => {
  it("not_comparable run does not render a winner marker", () => {
    const run = makeRun(
      "not_comparable",
      ["workspace snapshot mismatch"],
      {
        baseline: { pass_rate: 1.0, n_cells: 3, mean_latency_ms: 100, caveats: [], pass_at_k: { "1": 1.0 } },
        candidate: { pass_rate: 0.8, n_cells: 3, mean_latency_ms: 150, caveats: [], pass_at_k: { "1": 0.8 } },
      }
    );
    const { container } = render(<DecisionSummary run={run} />);

    const text = container.textContent ?? "";

    // The verdict text itself should be "not_comparable"
    expect(text).toContain("not_comparable");

    // Must NOT display winner-indicating terms
    const winnerPatterns = ["winner", "🏆", "✅ better", "best", "wins"];
    for (const pattern of winnerPatterns) {
      expect(text.toLowerCase()).not.toContain(pattern.toLowerCase());
    }
  });

  it("low_sample caveat is visible when present in configuration stats", () => {
    const run = makeRun(
      "inconclusive",
      [],
      {
        baseline: {
          pass_rate: 1.0,
          n_cells: 1,
          mean_latency_ms: 100,
          caveats: ["low_sample"],
          pass_at_k: { "1": 1.0 },
        },
      }
    );
    const { container } = render(<DecisionSummary run={run} />);

    const text = container.textContent ?? "";

    // "low sample" warning must be rendered somewhere in the component
    expect(text.toLowerCase()).toContain("low sample");
  });
});
