import { z } from "zod";

/**
 * Safe id regex mirroring micro_eval.models.configuration.SAFE_ID_RE
 * (`^[A-Za-z0-9_.:-]+$`) plus a negative lookahead rejecting ids composed
 * only of dots (e.g. "." or ".."), because ids are used to build
 * `tasks/<id>.yaml` paths on the Python side (GRO-549/GRO-550).
 */
export const SAFE_ID_RE = /^(?!\.+$)[A-Za-z0-9_.:-]+$/;

/**
 * Relative task-file path validator for `config remove-task --path` and the
 * tasks DELETE route (GRO-550 follow-up, F6/N13). Mirrors Python's
 * `micro_eval.config.editor.validate_relative_path` exactly rather than a
 * narrower ASCII/`.yaml`-only regex: non-empty; no backslash or control
 * character (< 0x20, which also covers NUL); not absolute (no leading `/`);
 * no Windows drive prefix (e.g. `C:`); every `/`-separated segment must be
 * non-empty and not `.` or `..`. Unlike the old TASK_PATH_RE this does not
 * require a `.yaml` extension and accepts any other character (e.g. non-ASCII
 * path segments), matching the Python behavior byte for byte.
 */
export function isSafeTaskPath(raw: string): boolean {
  if (typeof raw !== "string" || raw === "") return false;
  if (raw.includes("\\")) return false;
  if (raw.startsWith("/") || /^[A-Za-z]:/.test(raw)) return false;
  const segments = raw.split("/");
  // The .micro-eval runtime directory (locks, audit log, runs) is reserved.
  if (segments[0] === ".micro-eval") return false;
  for (const segment of segments) {
    if (segment === "" || segment === "." || segment === "..") return false;
    for (let i = 0; i < segment.length; i += 1) {
      if (segment.charCodeAt(i) < 0x20) return false;
    }
  }
  return true;
}

/**
 * Non-blank string: `.min(1)` alone still accepts whitespace-only values
 * (e.g. `" "`); the trim refine rejects those too (N12), matching the
 * intent of every required name/prompt field even though Pydantic's plain
 * `str` type does not enforce it itself.
 */
function nonBlankString(message: string) {
  return z.string().min(1).refine((value) => value.trim().length > 0, { message });
}

// ---------------------------------------------------------------------------
// Write-path input schemas (mirror micro_eval.models.configuration / task)
// ---------------------------------------------------------------------------

export const InputModeSchema = z.enum(["stdin", "file"]);
export const OutputModeSchema = z.enum(["stdout", "file", "directory"]);

export const AgentSpecInputSchema = z.object({
  name: nonBlankString("agent.name must not be blank"),
  command: z.array(z.string().min(1)).min(1),
  input_mode: InputModeSchema.default("stdin"),
  output_mode: OutputModeSchema.default("stdout"),
  // Mirrors AgentSpec.timeout_s's Pydantic default (300s) instead of forcing
  // every caller to specify it (F8).
  timeout_s: z.number().positive().default(300),
  env: z.record(z.string(), z.string()).default({}),
  required_secrets: z
    .array(
      z.string().refine((value) => value.startsWith("MICRO_EVAL_SECRET_"), {
        message: "required_secrets must use MICRO_EVAL_SECRET_* names",
      }),
    )
    .default([]),
});

export const ConfigurationInputSchema = z.object({
  id: z.string().regex(SAFE_ID_RE, "invalid configuration id"),
  name: nonBlankString("name must not be blank"),
  agent: AgentSpecInputSchema,
  repetitions: z.number().int().min(1).default(1),
  role: z.string().nullable().default(null),
  skills_profile: z.record(z.string(), z.unknown()).default({}),
  parameters: z.record(z.string(), z.unknown()).default({}),
});

// Mirrors ExpectationSpec.type: Pydantic accepts any string, but the editor
// (and the CLI's model_validator) only ever produces these four kinds; the
// enum catches typos in the form/API boundary before they reach the CLI (F8).
export const ExpectationTypeSchema = z.enum(["exit_code", "contains", "file_exists", "command"]);

// The form edits the four known types; any other `type` (the Python
// ExpectationSpec accepts free strings) is carried through untouched so
// editing a task never drops an expectation it cannot render (round-13).
export const ExpectationInputSchema = z
  .object({
    type: z.string().min(1),
    // Mirrors ExpectationSpec.value: str | int | None (N12) — a bare
    // z.number() would also accept 1.5, which Pydantic's `int` rejects.
    value: z.union([z.string(), z.number().int()]).nullable().default(null),
    path: z.string().nullable().default(null),
    stream: z.string().default("output"),
    // Mirrors ExpectationSpec.validate_expectation: a "command" expectation's
    // argv entries must be non-empty strings.
    command: z.array(z.string().min(1)).nullable().default(null),
    cwd: z.string().nullable().default(null),
    timeout_s: z.number().default(30),
  })
  .loose()
  .superRefine((value, ctx) => {
    if (value.type === "command" && (!value.command || value.command.length === 0)) {
      ctx.addIssue({
        code: "custom",
        path: ["command"],
        message: "command expectation requires a non-empty command",
      });
    }
  });

export const WorkspaceTypeSchema = z.enum(["blank", "files", "git_repo"]);

// Mirror micro_eval.models.task's IsolationLevel / TrustLevel / NetworkPolicy
// enums (F7/F8) so advanced workspace fields round-trip without drift.
export const IsolationLevelSchema = z.enum(["logical", "os_policy", "container", "vm"]);
export const TrustLevelSchema = z.enum(["trusted", "semi_trusted", "untrusted", "adversarial"]);
export const NetworkPolicySchema = z.enum(["full", "allowlist", "none"]);

export const FixtureSourceInputSchema = z.object({
  path: z.string().min(1),
  digest: z.string().nullable().optional(),
});

export const ToolchainInputSchema = z.object({
  runtime: z.string().nullable().optional(),
  lockfile: z.string().nullable().optional(),
});

const BLANK_WORKSPACE_INPUT = {
  type: "blank" as const,
  path: null,
  ref: null,
  files: [] as string[],
  setup: [] as string[][],
};

export const WorkspaceInputSchema = z.object({
  type: WorkspaceTypeSchema.default("blank"),
  path: z.string().nullable().default(null),
  ref: z.string().nullable().default(null),
  files: z.array(z.string()).default([]),
  setup: z.array(z.array(z.string())).default([]),
  // Advanced fields (spec §3.4.5/§3.4.3) are optional and left untouched by
  // the basic Task form; TaskForm.tsx merges them back in on edit (F7) so a
  // round trip through the form never drops them.
  isolation_level: IsolationLevelSchema.optional(),
  trust_level: TrustLevelSchema.optional(),
  network_policy: NetworkPolicySchema.nullable().optional(),
  fixtures: z.array(FixtureSourceInputSchema).optional(),
  toolchain: ToolchainInputSchema.nullable().optional(),
});

export const TaskInputSchema = z.object({
  id: z.string().regex(SAFE_ID_RE, "invalid task id"),
  name: nonBlankString("name must not be blank"),
  description: z.string().default(""),
  input_payload: nonBlankString("input_payload must not be blank"),
  expected_output: z.string().nullable().default(null),
  // Mirrors TaskSpec.rubric: a free-text string, a structured
  // {text, dimensions} object (RubricSpec), or absent. RubricSpec.dimensions
  // is `list[str | dict[str, Any]]` (N12), not an unknown grab-bag.
  rubric: z
    .union([
      z.string(),
      z.object({
        text: z.string().optional(),
        dimensions: z.array(z.union([z.string(), z.record(z.string(), z.unknown())])).optional(),
      }),
    ])
    .nullable()
    .default(null),
  expectations: z.array(ExpectationInputSchema).default([]),
  workspace: WorkspaceInputSchema.default(BLANK_WORKSPACE_INPUT),
  business_impact_tier: z.number().int().default(3),
  tags: z.array(z.string()).default([]),
  // Conversational evaluation fields (TaskSpec.scenario / expected_outcome /
  // user_description); optional and nullable so the basic form can omit them
  // while TaskForm.tsx's edit merge (F7) preserves any existing value.
  // NOTE: revision_id is intentionally NOT part of this schema — it is
  // derived server-side from the task file's content (loader.py hashes the
  // file on load), so it must never be sent by the client.
  scenario: z.string().nullable().optional(),
  expected_outcome: z.string().nullable().optional(),
  user_description: z.string().nullable().optional(),
});

export type AgentSpecInput = z.infer<typeof AgentSpecInputSchema>;
export type ConfigurationInput = z.infer<typeof ConfigurationInputSchema>;
export type ExpectationInput = z.infer<typeof ExpectationInputSchema>;
export type WorkspaceInput = z.infer<typeof WorkspaceInputSchema>;
export type TaskInput = z.infer<typeof TaskInputSchema>;

// ---------------------------------------------------------------------------
// Read-path schema for `micro-eval config show` (GRO-549 CLI contract)
// ---------------------------------------------------------------------------
//
// The CLI dumps ConfigurationSpec/TaskSpec via Pydantic model_dump(mode="json")
// with nested schema_version stripped. These schemas type the fields the UI needs
// and stay loose (`.loose()`) on the rest so new Pydantic fields never break
// parsing here.

export const AgentDraftSchema = z
  .object({
    name: z.string(),
    command: z.array(z.string()),
    input_mode: InputModeSchema,
    output_mode: OutputModeSchema,
    timeout_s: z.number(),
    env: z.record(z.string(), z.string()).default({}),
    required_secrets: z.array(z.string()).default([]),
  })
  .loose();

export const ConfigurationDraftSchema = z
  .object({
    id: z.string(),
    name: z.string(),
    agent: AgentDraftSchema,
    repetitions: z.number().int().default(1),
    role: z.string().nullable().default(null),
    skills_profile: z.record(z.string(), z.unknown()).default({}),
    parameters: z.record(z.string(), z.unknown()).default({}),
  })
  .loose();

export const ConfigurationErrorSchema = z.object({
  index: z.number().int(),
  id: z.string().nullable(),
  error: z.string(),
});

export const TaskDraftSchema = z
  .object({
    id: z.string(),
    name: z.string(),
    description: z.string().default(""),
    input_payload: z.string(),
    expected_output: z.string().nullable().default(null),
    rubric: z.union([z.string(), z.record(z.string(), z.unknown())]).nullable().default(null),
    expectations: z.array(z.record(z.string(), z.unknown())).default([]),
    workspace: z.record(z.string(), z.unknown()).default({}),
    business_impact_tier: z.number().int().default(3),
    tags: z.array(z.string()).default([]),
  })
  .loose();

export const TaskEntrySchema = z.object({
  path: z.string(),
  task: TaskDraftSchema.nullable(),
  error: z.string().nullable(),
});

export const ProjectDraftSchema = z.object({
  // Cross-module DTO version (Python `DRAFT_SCHEMA_VERSION`); nested specs
  // are dumped without their own schema_version to match hand-authored YAML.
  schema_version: z.literal("1.0"),
  project_name: z.string(),
  description: z.string().default(""),
  configurations: z.array(ConfigurationDraftSchema).default([]),
  configuration_errors: z.array(ConfigurationErrorSchema).default([]),
  tasks: z.array(TaskEntrySchema).default([]),
  warnings: z.array(z.string()).default([]),
});

export type AgentDraft = z.infer<typeof AgentDraftSchema>;
export type ConfigurationDraft = z.infer<typeof ConfigurationDraftSchema>;
export type ConfigurationError = z.infer<typeof ConfigurationErrorSchema>;
export type TaskDraft = z.infer<typeof TaskDraftSchema>;
export type TaskEntry = z.infer<typeof TaskEntrySchema>;
export type ProjectDraft = z.infer<typeof ProjectDraftSchema>;

// ---------------------------------------------------------------------------
// Raw eval.yaml read/write schemas (GRO-550 follow-up N1, hardened Advanced
// tab). `config show-raw` prints the file text with declared secret values
// replaced by `[REDACTED:<NAME>]`; `config set-raw` prints `{"saved": true}`
// on success, never the draft.
// ---------------------------------------------------------------------------

export const RawConfigSchema = z.object({
  content: z.string(),
  redacted: z.boolean(),
});

export const SetRawResultSchema = z.object({
  saved: z.literal(true),
});

export type RawConfig = z.infer<typeof RawConfigSchema>;

// ---------------------------------------------------------------------------
// Plan preview (`GET /api/workspaces/[id]/plan-summary`), reduced from the
// `workspace enqueue --dry-run` output.
// ---------------------------------------------------------------------------

export const PlanSummarySchema = z.object({
  tasks: z.number().int(),
  configurations: z.number().int(),
  repetitions: z.number().int(),
  repetitions_uniform: z.boolean(),
  total_cells: z.number().int(),
  agent_commands: z.array(z.string()),
  plan_digest: z.string().nullable(),
});

export type PlanSummary = z.infer<typeof PlanSummarySchema>;
