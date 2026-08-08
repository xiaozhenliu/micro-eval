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
  sandbox_policy: z.string().nullable().default(null),
  network_policy: z.string().nullable().default(null),
  toolchain_fingerprint: z.string().nullable().default(null),
  fixture_digests: z.record(z.string(), z.string()).default({}),
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
  evaluator_meta: z.record(z.string(), z.union([z.string(), z.number(), z.boolean(), z.null()])).nullable().default(null),
  rubric_hash: z.string().nullable().default(null),
  comment: z.string().default(""),
  evidence_refs: z.array(z.string()).default([]),
  created_at: z.string().default(""),
}).superRefine((value, ctx) => {
  // Mirror Python EvaluationResult.pass_fail_requires_evidence: a pass/fail
  // verdict must be backed by at least one evidence reference (#6).
  if (value.pass_fail !== null && value.evidence_refs.length === 0) {
    ctx.addIssue({
      code: "custom",
      path: ["evidence_refs"],
      message: "pass_fail evaluation requires evidence_refs",
    });
  }
});

export const CostMetricSchema = z.object({
  schema_version: z.string().default("1.0"),
  amount: z.number().nullable().default(null),
  currency: z.string().default("USD"),
  source: z.string().default("unavailable"),
});

export const ConfigurationStatsSchema = z.preprocess((value) => {
  if (value && typeof value === "object" && "total" in value) {
    const legacy = value as Record<string, unknown>;
    const total = Number(legacy.total ?? 0);
    const passRate = Number(legacy.pass_rate ?? 0);
    return {
      schema_version: legacy.schema_version ?? "1.0",
      n_cells: total,
      n_successful: total,
      pass_rate: legacy.pass_rate ?? null,
      pass_at_k: total === 1 ? { 1: passRate } : null,
      pass_hat_k: total === 1 ? { 1: passRate } : null,
      mean_latency_ms: typeof legacy.mean_latency_s === "number" ? legacy.mean_latency_s * 1000 : null,
      median_latency_ms: typeof legacy.median_latency_s === "number" ? legacy.median_latency_s * 1000 : null,
      total_cost: typeof legacy.cost_usd === "number" ? { amount: legacy.cost_usd, currency: "USD", source: "legacy_cost_usd" } : null,
      denominator_policy: "include_failed",
      caveats: total < 3 ? ["low_sample"] : [],
    };
  }
  return value;
}, z.object({
  schema_version: z.string().default("1.0"),
  n_cells: z.number().int().default(0),
  n_successful: z.number().int().default(0),
  pass_rate: z.number().nullable().default(null),
  pass_at_k: z.record(z.string(), z.number()).nullable().default(null),
  pass_hat_k: z.record(z.string(), z.number()).nullable().default(null),
  mean_latency_ms: z.number().nullable().default(null),
  median_latency_ms: z.number().nullable().default(null),
  total_cost: CostMetricSchema.nullable().default(null),
  denominator_policy: z.enum(["include_failed", "exclude_failed"]).default("include_failed"),
  caveats: z.array(z.string()).default([]),
}));

export const AggregationResultSchema = z.preprocess((value) => {
  if (value && typeof value === "object" && !("per_configuration" in value)) {
    const raw = value as Record<string, unknown>;
    const { schema_version, ...perConfiguration } = raw;
    return { schema_version: schema_version ?? "1.0", per_configuration: perConfiguration };
  }
  return value;
}, z.object({
  schema_version: z.string().default("1.0"),
  per_configuration: z.record(z.string(), ConfigurationStatsSchema).default({}),
}));


export const TraceRefSchema = z.object({
  schema_version: z.string().default("1.0"),
  trace_id: z.string(),
  provider: z.string(),
  external_url: z.string().nullable().default(null),
  cost: CostMetricSchema.nullable().default(null),
  summary: z.record(z.string(), z.union([z.string(), z.number(), z.boolean(), z.null()])).nullable().default(null),
});

export const DecisionReportSchema = z.preprocess((value) => {
  if (value && typeof value === "object") {
    const raw = value as Record<string, unknown>;
    return {
      ...raw,
      timestamp: raw.timestamp ?? raw.created_at ?? "",
      created_at: raw.created_at ?? raw.timestamp ?? "",
      decision_report_id: raw.decision_report_id ?? "",
    };
  }
  return value;
}, z.object({
  schema_version: z.string().default("1.0"),
  decision_report_id: z.string().default(""),
  verdict: z.enum(["improved", "regressed", "mixed", "inconclusive", "not_comparable", "needs_human_review"]),
  confidence: z.enum(["high", "medium", "low"]).default("low"),
  evaluation_refs: z.array(z.string()).default([]),
  evidence_refs: z.array(z.string()).default([]),
  caveats: z.array(z.string()).default([]),
  aggregation: AggregationResultSchema.default({ schema_version: "1.0", per_configuration: {} }),
  recommended_action: z.string().default("review evidence"),
  timestamp: z.string().default(""),
  created_at: z.string().default(""),
}));

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
  stdout_truncated: z.boolean().default(false),
  stderr_truncated: z.boolean().default(false),
  output_truncated: z.boolean().default(false),
  artifact_refs: z.array(z.string()).default([]),
  evidence_refs: z.array(z.string()).default([]),
  evaluation_refs: z.array(z.string()).default([]),
  trace_refs: z.array(z.string()).default([]),
  cell_snapshot: CellSnapshotSchema.nullable().default(null),
  snapshot_gate_result: SnapshotGateResultSchema.nullable().default(null),
  // Conversational evaluation metadata (backward compatible)
  conversation_turns: z.number().int().default(0),
  conversation_ref: z.string().nullable().default(null),
});

export const ServerContextSchema = z.object({
  schema_version: z.string().default("1.0"),
  workspace_id: z.string(),
  owner: z.string(),
  template_id: z.string().nullable().default(null),
  template_version: z.string().nullable().default(null),
  job_id: z.string(),
  server_name: z.string(),
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
  execution_order: z.array(z.string()).default([]),
  execution_seed: z.number().int().nullable().default(null),
  migration_warnings: z.array(z.string()).default([]),
  same_start_snapshot: SameStartSnapshotSchema.nullable().default(null),
  replay_canonical: ReplayCanonicalSchema.nullable().default(null),
  artifacts: z.array(ArtifactRefSchema).default([]),
  evidence: z.array(EvidenceItemSchema).default([]),
  traces: z.array(TraceRefSchema).default([]),
  evaluations: z.array(EvaluationResultSchema).default([]),
  decision: DecisionReportSchema.nullable().default(null),
  denominator_policy: z.enum(["include_failed", "exclude_failed"]).default("include_failed"),
  owner: z.string().nullable().default(null),
  server_context: ServerContextSchema.nullable().default(null),
});

export const WorkspaceMetaSchema = z.object({
  schema_version: z.string().default("1.0"),
  workspace_id: z.string(),
  name: z.string(),
  owner: z.string(),
  template_id: z.string().nullable().default(null),
  template_version: z.string().nullable().default(null),
  created_at: z.string(),
  last_run_at: z.string().nullable().default(null),
  run_count: z.number().int().default(0),
  description: z.string().default(""),
  status: z.string().default("active"),
});

export const JobSchema = z.object({
  job_id: z.string(),
  workspace_id: z.string(),
  owner: z.string(),
  status: z.string(),
  enqueued_at: z.string(),
  started_at: z.string().nullable().default(null),
  finished_at: z.string().nullable().default(null),
  run_id: z.string().nullable().default(null),
  error: z.string().nullable().default(null),
  progress: z.any().nullable().default(null),
  cancel_requested_at: z.string().nullable().default(null),
  cancelled_by: z.string().nullable().default(null),
});

export type WorkspaceMeta = z.infer<typeof WorkspaceMetaSchema>;
export type Job = z.infer<typeof JobSchema>;

export type ArtifactRef = z.infer<typeof ArtifactRefSchema>;
export type EvidenceItem = z.infer<typeof EvidenceItemSchema>;
export type TraceRef = z.infer<typeof TraceRefSchema>;
export type EvaluationResult = z.infer<typeof EvaluationResultSchema>;
export type CostMetric = z.infer<typeof CostMetricSchema>;
export type ConfigurationStats = z.infer<typeof ConfigurationStatsSchema>;
export type AggregationResult = z.infer<typeof AggregationResultSchema>;
export type CellResult = z.infer<typeof CellResultSchema>;
export type DecisionReport = z.infer<typeof DecisionReportSchema>;
export type Run = z.infer<typeof RunSchema>;
