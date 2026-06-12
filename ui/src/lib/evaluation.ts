import crypto from "node:crypto";
import path from "node:path";
import fs from "node:fs";
import type { EvidenceItem, EvaluationResult, Run } from "./schema";

export interface HumanEvaluationInput {
  pass_fail: "pass" | "fail" | null;
  score: number | null;
  scores: Record<string, number>;
  comment: string;
  evaluator: string;
}

export function safePathSegment(value: string): string {
  const safe = value.replace(/[^A-Za-z0-9_.:-]+/g, "-").replace(/^[.-]+|[.-]+$/g, "");
  return safe || "unknown";
}

export function redactSecrets(text: string): string {
  let redacted = text;
  for (const [name, value] of Object.entries(process.env)) {
    if (!name.startsWith("MICRO_EVAL_SECRET_") || !value) continue;
    redacted = redacted.split(value).join(`[REDACTED:${name}]`);
  }
  return redacted;
}

export function buildHumanEvaluation(cellId: string, input: HumanEvaluationInput): { evaluation: EvaluationResult; evidence: EvidenceItem } {
  const createdAt = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
  const digest = crypto
    .createHash("sha256")
    .update(JSON.stringify({ cellId, input, createdAt }))
    .digest("hex")
    .slice(0, 12);
  const evaluationId = `${cellId}::human::${digest}`;
  const evidenceId = `${cellId}::evidence::human-${digest}`;
  const comment = redactSecrets(input.comment).slice(0, 500);
  return {
    evaluation: {
      schema_version: "1.0",
      evaluation_id: evaluationId,
      cell_id: cellId,
      evaluator_type: "human",
      evaluator: input.evaluator,
      pass_fail: input.pass_fail,
      score: input.score,
      scores: input.scores,
      evaluator_meta: null,
      rubric_hash: null,
      comment,
      evidence_refs: [evidenceId],
      created_at: createdAt,
    },
    evidence: {
      schema_version: "1.0",
      evidence_id: evidenceId,
      kind: "annotation",
      summary: comment || `human evaluation: ${input.pass_fail ?? "unscored"}`,
      source_kind: "evaluation_id",
      source_ref: evaluationId,
      cell_id: cellId,
      status: input.pass_fail === "pass" ? "passed" : input.pass_fail === "fail" ? "failed" : "skipped",
      severity: "info",
      artifact_refs: [],
      metadata: { evaluator: input.evaluator },
    },
  };
}

export function appendEvaluationToRun(run: Run, evaluation: EvaluationResult, evidence: EvidenceItem): Run {
  const evaluations = [...run.evaluations.filter((item) => item.evaluation_id !== evaluation.evaluation_id), evaluation];
  const evidenceItems = [...run.evidence.filter((item) => item.evidence_id !== evidence.evidence_id), evidence];
  const results = run.results.map((result) => {
    if (result.cell_id !== evaluation.cell_id) return result;
    return {
      ...result,
      pass_fail: evaluation.pass_fail,
      score: evaluation.score,
      evidence_refs: Array.from(new Set([...result.evidence_refs, ...evaluation.evidence_refs])),
      evaluation_refs: Array.from(new Set([...result.evaluation_refs, evaluation.evaluation_id])),
    };
  });
  const updated: Run = { ...run, evaluations, evidence: evidenceItems, results };
  return { ...updated, decision: recomputeDecision(updated) };
}

export function appendEvaluationFile(runDir: string, cellId: string, evaluation: EvaluationResult): void {
  const cellDir = path.join(runDir, "cells", safePathSegment(cellId));
  fs.mkdirSync(cellDir, { recursive: true });
  const evaluationPath = path.join(cellDir, "evaluation.json");
  const existing = fs.existsSync(evaluationPath) ? JSON.parse(fs.readFileSync(evaluationPath, "utf-8")) as EvaluationResult[] : [];
  fs.writeFileSync(evaluationPath, JSON.stringify([...existing, evaluation], null, 2));
}

export function recomputeDecision(run: Run): Run["decision"] {
  const policy = run.denominator_policy ?? "include_failed";
  const perConfiguration: NonNullable<Run["decision"]>["aggregation"]["per_configuration"] = {};
  const configurationIds = Array.from(new Set(run.results.map((result) => result.configuration_id)));
  for (const configurationId of configurationIds) {
    const results = run.results.filter((result) => result.configuration_id === configurationId);
    const nCells = results.length;
    // Successful cells: those with a binary outcome (pass or fail, not error/timeout)
    const successfulResults = results.filter((result) => result.status === "pass" || result.status === "fail");
    const nSuccessful = successfulResults.length;
    // denominator pool depends on policy
    const denominatorResults = policy === "exclude_failed" ? successfulResults : results;
    const denominator = denominatorResults.length;
    const passed = denominatorResults.filter((result) =>
      result.pass_fail == null ? result.status === "pass" : result.pass_fail === "pass"
    ).length;
    const hasBinary = results.some((result) => result.pass_fail != null || result.status === "pass" || result.status === "fail");
    const passRate = hasBinary && denominator ? passed / denominator : null;
    const latenciesMs = results.map((result) => result.latency_s * 1000);
    perConfiguration[configurationId] = {
      schema_version: "1.0",
      n_cells: nCells,
      n_successful: nSuccessful,
      pass_rate: passRate,
      pass_at_k: passRate == null ? null : passAtK(denominator, passed),
      pass_hat_k: passRate == null ? null : passHatK(denominator, passRate),
      mean_latency_ms: latenciesMs.length ? latenciesMs.reduce((sum, value) => sum + value, 0) / latenciesMs.length : null,
      median_latency_ms: median(latenciesMs),
      total_cost: { schema_version: "1.0", amount: null, currency: "USD", source: "unavailable" },
      denominator_policy: policy,
      caveats: nSuccessful < 3 ? ["low_sample"] : [],
    };
  }
  const evaluationRefs = run.results.flatMap((result) => result.evaluation_refs);
  const evidenceRefs = run.results.flatMap((result) => result.evidence_refs);
  const snapshotWarnings = run.results.filter((result) => result.snapshot_gate_result && result.snapshot_gate_result.status !== "pass");
  const lowSample = Object.values(perConfiguration).some((stats) => stats.caveats.includes("low_sample"));
  const caveats = dedupe([
    ...run.migration_warnings,
    ...(run.same_start_snapshot?.caveats ?? []),
    ...snapshotWarnings.map((result) => `snapshot gate warning for ${result.cell_id}: ${(result.snapshot_gate_result?.mismatch_fields ?? []).join(", ") || "cleanup/caveat"}`),
    ...(run.results.length < run.cells.length ? ["run is partial; not all cells completed"] : []),
    ...(run.configurations.length < 2 ? ["single configuration run cannot produce comparative verdict"] : []),
    ...(lowSample ? ["low_sample"] : []),
    ...Object.entries(perConfiguration).filter(([, stats]) => stats.caveats.includes("low_sample")).map(([id]) => `low sample size for ${id}: repetitions < 3`),
  ]);
  let verdict: NonNullable<Run["decision"]>["verdict"] = "inconclusive";
  let recommendedAction = "review evidence and complete P0-b comparability gate";
  if (snapshotWarnings.length) {
    verdict = "not_comparable";
    recommendedAction = "fix same-start snapshot mismatches before comparing configurations";
  }
  if (!evaluationRefs.length || !evidenceRefs.length) {
    verdict = "needs_human_review";
    recommendedAction = "collect evaluation evidence before deciding";
  }
  const timestamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
  return {
    schema_version: "1.0",
    decision_report_id: `${run.id}::decision::${timestamp}`,
    verdict,
    confidence: "low",
    evaluation_refs: evaluationRefs,
    evidence_refs: evidenceRefs,
    caveats,
    aggregation: { schema_version: "1.0", per_configuration: perConfiguration },
    recommended_action: recommendedAction,
    timestamp,
    created_at: timestamp,
  };
}

function passAtK(n: number, c: number): Record<string, number> {
  const values: Record<string, number> = {};
  for (let k = 1; k <= n; k += 1) {
    values[String(k)] = n - c < k ? 1 : 1 - combination(n - c, k) / combination(n, k);
  }
  return values;
}

function passHatK(n: number, passRate: number): Record<string, number> {
  const values: Record<string, number> = {};
  for (let k = 1; k <= n; k += 1) {
    values[String(k)] = passRate ** k;
  }
  return values;
}

function combination(n: number, k: number): number {
  if (k < 0 || k > n) return 0;
  let result = 1;
  for (let i = 1; i <= k; i += 1) {
    result = (result * (n - i + 1)) / i;
  }
  return result;
}

function dedupe(values: string[]): string[] {
  return Array.from(new Set(values));
}

function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) return sorted[mid];
  return (sorted[mid - 1] + sorted[mid]) / 2;
}
