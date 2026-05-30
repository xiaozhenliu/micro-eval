import { z } from "zod";

export const RunResultSchema = z.object({
  task_id: z.string(),
  agent_name: z.string(),
  status: z.enum(["pass", "fail", "error", "timeout"]),
  score: z.number().nullable(),
  output_summary: z.string(),
  cost_usd: z.number().nullable(),
  latency_s: z.number(),
  failure_mode: z.string().nullable(),
});

export const EnvironmentSchema = z.object({
  git_commit: z.string(),
  config_hash: z.string(),
  python_version: z.string(),
  timestamp: z.string(),
});

export const RunSchema = z.object({
  id: z.string(),
  schema_version: z.literal("1.0"),
  timestamp: z.string(),
  baseline_agent: z.string(),
  candidate_agent: z.string(),
  tasks: z.array(z.string()),
  results: z.array(RunResultSchema),
  environment: EnvironmentSchema,
  execution_order: z.enum(["parallel", "sequential"]),
});

export type RunResult = z.infer<typeof RunResultSchema>;
export type Environment = z.infer<typeof EnvironmentSchema>;
export type Run = z.infer<typeof RunSchema>;
