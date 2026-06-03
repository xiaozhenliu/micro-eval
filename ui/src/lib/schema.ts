import { z } from "zod";

export const ArtifactRefSchema = z.object({
  schema_version: z.string().default("1.0"),
  artifact_id: z.string(),
  kind: z.string(),
  path: z.string(),
  sha256: z.string(),
  size_bytes: z.number(),
  media_type: z.string().default("text/plain"),
  redacted: z.boolean().default(true),
  warning: z.string().nullable().default(null),
});

export const EvidenceItemSchema = z.object({
  schema_version: z.string().default("1.0"),
  evidence_id: z.string(),
  kind: z.string(),
  summary: z.string(),
  source_kind: z.string().nullable().default(null),
  source_ref: z.string().nullable().default(null),
  cell_id: z.string().nullable().default(null),
  status: z.string().default("passed"),
  severity: z.string().default("info"),
  artifact_refs: z.array(z.string()).default([]),
  metadata: z.record(z.string(), z.union([z.string(), z.number(), z.boolean(), z.null()])).default({}),
});

export const SameStartSnapshotSchema = z.object({
  schema_version: z.string().default("1.0"),
  workspace_type: z.string(),
  git_commit: z.string().nullable().default(null),
  dirty: z.boolean().nullable().default(null),
  config_hash: z.string(),
  configuration_digests: z.record(z.string(), z.string()).default({}),
  task_revisions: z.record(z.string(), z.string()).default({}),
  python_version: z.string(),
  setup_commands_digest: z.string().nullable().default(null),
  guardrails_digest: z.string().default(""),
  sandbox_resource_limits: z.record(z.string(), z.union([z.string(), z.number(), z.boolean(), z.null()])).nullable().default(null),
  workspace_map: z.record(z.string(), z.string().nullable()).nullable().default(null),
  timestamp: z.string(),
  caveats: z.array(z.string()).default([]),
});

export const ReplayCanonicalSchema = z.object({
  schema_version: z.string().default("1.0"),
  tool_version: z.string(),
  config_hash: z.string(),
  task_ids: z.array(z.string()).default([]),
  task_revisions: z.record(z.string(), z.string()).default({}),
  configuration_ids: z.array(z.string()).default([]),
  configuration_digests: z.record(z.string(), z.string()).default({}),
  workspace_type: z.string().default("blank"),
  git_commit: z.string().nullable().default(null),
  workspace_map: z.record(z.string(), z.string().nullable()).nullable().default(null),
  workspace_fingerprint: z.string().default(""),
  setup_commands_digest: z.string().nullable().default(null),
  guardrails_digest: z.string().default(""),
  max_concurrency: z.number(),
  digest: z.string(),
});

export const CellSnapshotSchema = z.object({
  schema_version: z.string().default("1.0"),
  workspace_path: z.string(),
  git_commit: z.string().nullable().default(null),
  dirty: z.boolean().nullable().default(null),
  setup_exit_code: z.number().int().nullable().default(null),
  timestamp: z.string(),
  cleanup_status: z.string().nullable().default(null),
  cleanup_error: z.string().nullable().default(null),
});

export const SnapshotGateResultSchema = z.object({
  schema_version: z.string().default("1.0"),
  status: z.enum(["pass", "warn", "fail"]),
  mismatch_fields: z.array(z.string()).default([]),
  gate_version: z.string().default("1.0"),
  caveats: z.array(z.string()).default([]),
});

export const EvaluationResultSchema = z.object({
  schema_version: z.string().default("1.0"),
  evaluation_id: z.string(),
  cell_id: z.string(),
  evaluator_type: z.string().default("validator"),
  evaluator: z.string(),
  pass_fail: z.enum(["pass", "fail"]).nullable().default(null),
  score: z.number().nullable().default(null),
  scores: z.record(z.string(), z.number()).default({}),
  comment: z.string().default(""),
  evidence_refs: z.array(z.string()).default([]),
  created_at: z.string().default(""),
});

export const AggregationStatsSchema = z.object({
  schema_version: z.string().default("1.0"),
  total: z.number().int().default(0),
  passed: z.number().int().default(0),
  pass_rate: z.number().default(0),
  mean_latency_s: z.number().nullable().default(null),
  median_latency_s: z.number().nullable().default(null),
  cost_usd: z.number().nullable().default(null),
});

export const DecisionReportSchema = z.object({
  schema_version: z.string().default("1.0"),
  verdict: z.enum(["improved", "regressed", "mixed", "inconclusive", "not_comparable", "needs_human_review"]),
  confidence: z.string(),
  evaluation_refs: z.array(z.string()).default([]),
  evidence_refs: z.array(z.string()).default([]),
  caveats: z.array(z.string()).default([]),
  aggregation: z.record(z.string(), AggregationStatsSchema).default({}),
  recommended_action: z.string(),
  created_at: z.string(),
});

export const CellResultSchema = z.object({
  schema_version: z.string().default("1.0"),
  cell_id: z.string(),
  run_id: z.string(),
  task_id: z.string(),
  configuration_id: z.string(),
  configuration_name: z.string(),
  repetition: z.number().int(),
  status: z.enum(["pass", "fail", "error", "timeout"]),
  score: z.number().nullable().default(null),
  pass_fail: z.enum(["pass", "fail"]).nullable().default(null),
  output_summary: z.string().default(""),
  stdout_summary: z.string().default(""),
  stderr_summary: z.string().default(""),
  exit_code: z.number().int().nullable().default(null),
  latency_s: z.number().default(0),
  failure_mode: z.string().nullable().default(null),
  artifact_refs: z.array(z.string()).default([]),
  evidence_refs: z.array(z.string()).default([]),
  evaluation_refs: z.array(z.string()).default([]),
  cell_snapshot: CellSnapshotSchema.nullable().default(null),
  snapshot_gate_result: SnapshotGateResultSchema.nullable().default(null),
});

export const RunSchema = z.object({
  schema_version: z.string().default("1.0"),
  id: z.string(),
  project_name: z.string(),
  status: z.enum(["planned", "running", "completed", "failed", "partial"]),
  created_at: z.string(),
  completed_at: z.string().nullable().default(null),
  output_dir: z.string(),
  config_hash: z.string().default(""),
  tasks: z.array(z.string()).default([]),
  configurations: z.array(z.string()).default([]),
  cells: z.array(z.string()).default([]),
  results: z.array(CellResultSchema).default([]),
  migration_warnings: z.array(z.string()).default([]),
  same_start_snapshot: SameStartSnapshotSchema.nullable().default(null),
  replay_canonical: ReplayCanonicalSchema.nullable().default(null),
  artifacts: z.array(ArtifactRefSchema).default([]),
  evidence: z.array(EvidenceItemSchema).default([]),
  evaluations: z.array(EvaluationResultSchema).default([]),
  decision: DecisionReportSchema.nullable().default(null),
});

export type ArtifactRef = z.infer<typeof ArtifactRefSchema>;
export type EvidenceItem = z.infer<typeof EvidenceItemSchema>;
export type EvaluationResult = z.infer<typeof EvaluationResultSchema>;
export type CellResult = z.infer<typeof CellResultSchema>;
export type DecisionReport = z.infer<typeof DecisionReportSchema>;
export type Run = z.infer<typeof RunSchema>;
