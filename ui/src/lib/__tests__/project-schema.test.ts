/**
 * GRO-550: zod schemas mirroring micro_eval.config.editor's `config show`
 * contract and the write-path input models (ConfigurationSpec/TaskSpec).
 *
 * The golden fixture is produced by the real `config show` logic
 * (build_project_draft) on a fixture project seeded from init.py's starter
 * content — see scripts/generate-golden.py::_write_project_draft_fixture.
 */

import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import {
  ProjectDraftSchema,
  ConfigurationInputSchema,
  TaskInputSchema,
  ExpectationInputSchema,
  AgentSpecInputSchema,
  SAFE_ID_RE,
  isSafeTaskPath,
} from "../project-schema";

const GOLDEN_DIR = path.resolve(__dirname, "../../../../tests/contract/golden");
const projectDraftRaw: unknown = JSON.parse(
  fs.readFileSync(path.join(GOLDEN_DIR, "project-draft.json"), "utf-8"),
);

describe("ProjectDraftSchema parses the real config-show golden fixture", () => {
  it("parses without throwing", () => {
    expect(() => ProjectDraftSchema.parse(projectDraftRaw)).not.toThrow();
  });

  it("has 2 configurations and 1 task, matching the init.py starter project", () => {
    const draft = ProjectDraftSchema.parse(projectDraftRaw);
    expect(draft.project_name).toBe("demo-agent-eval");
    expect(draft.configurations).toHaveLength(2);
    expect(draft.configurations.map((c) => c.id).sort()).toEqual(["baseline", "candidate"]);
    expect(draft.configuration_errors).toEqual([]);
    expect(draft.tasks).toHaveLength(1);
    expect(draft.tasks[0].path).toBe("tasks/hello.yaml");
    expect(draft.tasks[0].error).toBeNull();
    expect(draft.tasks[0].task?.id).toBe("hello");
    expect(draft.warnings).toEqual([]);
  });

  it("configuration agent fields survive parsing", () => {
    const draft = ProjectDraftSchema.parse(projectDraftRaw);
    const baseline = draft.configurations.find((c) => c.id === "baseline");
    expect(baseline?.agent.command).toEqual(["cat"]);
    expect(baseline?.agent.input_mode).toBe("stdin");
    expect(baseline?.agent.output_mode).toBe("stdout");
  });
});

describe("SAFE_ID_RE", () => {
  it.each(["baseline", "a.b-c_d:e", "v1"])("accepts %j", (id) => {
    expect(SAFE_ID_RE.test(id)).toBe(true);
  });

  it.each([".", "..", "...", "a/b", ""])("rejects %j", (id) => {
    expect(SAFE_ID_RE.test(id)).toBe(false);
  });
});

const validConfiguration = {
  id: "baseline",
  name: "baseline",
  agent: {
    name: "baseline",
    command: ["cat"],
    timeout_s: 10,
  },
};

describe("ConfigurationInputSchema", () => {
  it("accepts a minimal valid configuration and fills defaults", () => {
    const parsed = ConfigurationInputSchema.parse(validConfiguration);
    expect(parsed.repetitions).toBe(1);
    expect(parsed.agent.input_mode).toBe("stdin");
    expect(parsed.agent.output_mode).toBe("stdout");
    expect(parsed.agent.env).toEqual({});
    expect(parsed.agent.required_secrets).toEqual([]);
  });

  it.each(["..", "a/b"])("rejects bad id %j", (id) => {
    const result = ConfigurationInputSchema.safeParse({ ...validConfiguration, id });
    expect(result.success).toBe(false);
  });

  it("rejects a required_secrets entry without the MICRO_EVAL_SECRET_ prefix", () => {
    const result = ConfigurationInputSchema.safeParse({
      ...validConfiguration,
      agent: { ...validConfiguration.agent, required_secrets: ["BAD_NAME"] },
    });
    expect(result.success).toBe(false);
  });

  it("accepts a required_secrets entry with the MICRO_EVAL_SECRET_ prefix", () => {
    const result = ConfigurationInputSchema.safeParse({
      ...validConfiguration,
      agent: { ...validConfiguration.agent, required_secrets: ["MICRO_EVAL_SECRET_API_KEY"] },
    });
    expect(result.success).toBe(true);
  });

  it("rejects an empty argv command", () => {
    const result = ConfigurationInputSchema.safeParse({
      ...validConfiguration,
      agent: { ...validConfiguration.agent, command: [] },
    });
    expect(result.success).toBe(false);
  });

  it("rejects repetitions: 0", () => {
    const result = ConfigurationInputSchema.safeParse({ ...validConfiguration, repetitions: 0 });
    expect(result.success).toBe(false);
  });

  // N12: whitespace-only name.
  it("rejects a whitespace-only name", () => {
    const result = ConfigurationInputSchema.safeParse({ ...validConfiguration, name: "   " });
    expect(result.success).toBe(false);
  });
});

describe("TaskInputSchema", () => {
  const validTask = { id: "hello", name: "Hello", input_payload: "hi" };

  it("accepts a minimal valid task and fills defaults", () => {
    const parsed = TaskInputSchema.parse(validTask);
    expect(parsed.description).toBe("");
    expect(parsed.expectations).toEqual([]);
    expect(parsed.workspace.type).toBe("blank");
    expect(parsed.business_impact_tier).toBe(3);
    expect(parsed.tags).toEqual([]);
  });

  it("rejects empty input_payload", () => {
    const result = TaskInputSchema.safeParse({ ...validTask, input_payload: "" });
    expect(result.success).toBe(false);
  });

  // N12: `.min(1)` alone still admits whitespace-only strings.
  it("rejects a whitespace-only input_payload", () => {
    const result = TaskInputSchema.safeParse({ ...validTask, input_payload: "   " });
    expect(result.success).toBe(false);
  });

  it("rejects a whitespace-only name", () => {
    const result = TaskInputSchema.safeParse({ ...validTask, name: "   " });
    expect(result.success).toBe(false);
  });

  it.each(["..", "a/b"])("rejects bad id %j", (id) => {
    const result = TaskInputSchema.safeParse({ ...validTask, id });
    expect(result.success).toBe(false);
  });

  it("accepts a structured rubric object", () => {
    const result = TaskInputSchema.safeParse({
      ...validTask,
      rubric: { text: "score for correctness", dimensions: ["correctness", { name: "style", weight: 0.2 }] },
    });
    expect(result.success).toBe(true);
  });

  // N12: RubricSpec.dimensions is `list[str | dict[str, Any]]`, not
  // arbitrary values.
  it("rejects a rubric.dimensions entry that is neither a string nor a record", () => {
    const result = TaskInputSchema.safeParse({
      ...validTask,
      rubric: { text: "x", dimensions: [42] },
    });
    expect(result.success).toBe(false);
  });

  it("accepts advanced workspace fields and conversational fields (F7 round trip)", () => {
    const result = TaskInputSchema.safeParse({
      ...validTask,
      scenario: "user reports a bug",
      expected_outcome: "agent reproduces and fixes it",
      user_description: "a terse, impatient user",
      workspace: {
        type: "git_repo",
        path: "/repo",
        ref: "main",
        files: [],
        setup: [["npm", "install"]],
        isolation_level: "os_policy",
        trust_level: "untrusted",
        network_policy: "none",
        fixtures: [{ path: "fixtures/a.json", digest: "sha256:abc" }],
        toolchain: { runtime: "node20", lockfile: "package-lock.json" },
      },
    });
    expect(result.success).toBe(true);
  });
});

// F8: zod <-> Pydantic drift fixes on the write-path schemas.
describe("ExpectationInputSchema (F8)", () => {
  it("rejects a command expectation with an empty argv", () => {
    const result = ExpectationInputSchema.safeParse({ type: "command", command: [] });
    expect(result.success).toBe(false);
  });

  it("rejects a command expectation with no command field at all", () => {
    const result = ExpectationInputSchema.safeParse({ type: "command" });
    expect(result.success).toBe(false);
  });

  it("accepts a command expectation with a non-empty argv", () => {
    const result = ExpectationInputSchema.safeParse({ type: "command", command: ["test", "-f", "out.txt"] });
    expect(result.success).toBe(true);
  });

  it("rejects a command expectation whose argv contains an empty string", () => {
    const result = ExpectationInputSchema.safeParse({ type: "command", command: ["test", ""] });
    expect(result.success).toBe(false);
  });

  // Round-13 review: the Python ExpectationSpec accepts any `type`; the form
  // passes unknown types through untouched instead of dropping them.
  it("passes an unknown expectation type through with its extra fields", () => {
    const result = ExpectationInputSchema.safeParse({ type: "regex_match", value: "x", pattern: "^x$" });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.type).toBe("regex_match");
      expect((result.data as Record<string, unknown>).pattern).toBe("^x$");
    }
  });

  it("still rejects an empty expectation type", () => {
    expect(ExpectationInputSchema.safeParse({ type: "", value: "x" }).success).toBe(false);
  });

  // N12: ExpectationSpec.value is `str | int | None`; a bare z.number() would
  // also accept floats.
  it("rejects a non-integer numeric value", () => {
    const result = ExpectationInputSchema.safeParse({ type: "exit_code", value: 1.5 });
    expect(result.success).toBe(false);
  });

  it("accepts an integer numeric value", () => {
    const result = ExpectationInputSchema.safeParse({ type: "exit_code", value: 1 });
    expect(result.success).toBe(true);
  });
});

describe("AgentSpecInputSchema (F8)", () => {
  const base = { name: "baseline", command: ["cat"] };

  it("parses without timeout_s, defaulting to 300 (Pydantic default)", () => {
    const parsed = AgentSpecInputSchema.parse(base);
    expect(parsed.timeout_s).toBe(300);
  });

  it("still accepts an explicit timeout_s", () => {
    const parsed = AgentSpecInputSchema.parse({ ...base, timeout_s: 10 });
    expect(parsed.timeout_s).toBe(10);
  });

  // N12: whitespace-only name.
  it("rejects a whitespace-only name", () => {
    const result = AgentSpecInputSchema.safeParse({ ...base, name: "   " });
    expect(result.success).toBe(false);
  });
});

describe("isSafeTaskPath (F6/N13, mirrors Python validate_relative_path)", () => {
  it.each([
    "tasks/hello.yaml",
    "hello.yaml",
    "a/b/c.yaml",
    "a.b-c_d.yaml",
    "tasks/my task.yaml",
    "任务/x.yaml",
  ])("accepts %j", (path) => {
    expect(isSafeTaskPath(path)).toBe(true);
  });

  it.each([
    "../secret.yaml",
    "tasks/../secret.yaml",
    "tasks/..",
    "..",
    "/etc/passwd.yaml",
    "../x",
    "/abs",
    "a//b",
    "a\\b",
    "C:x",
    "",
  ])("rejects %j", (path) => {
    expect(isSafeTaskPath(path)).toBe(false);
  });
});
