/**
 * GRO-551: unit tests for the pure agent-preset helpers used by
 * ConfigurationForm — argv construction, id slugification, env parsing,
 * and preset detection for the edit flow.
 */

import { describe, it, expect } from "vitest";
import { buildAgentSpec, slugifyId, parseEnvLines, detectPreset } from "../agent-presets";

describe("buildAgentSpec", () => {
  it("builds a claude-code command without a model", () => {
    const agent = buildAgentSpec("claude-code", {
      name: "baseline",
      timeoutS: 900,
      maxTurns: 10,
      env: {},
      requiredSecrets: [],
    });
    expect(agent.command).toEqual(["claude", "-p", "--permission-mode", "acceptEdits", "--max-turns", "10"]);
    expect(agent.input_mode).toBe("stdin");
    expect(agent.output_mode).toBe("stdout");
    expect(agent.timeout_s).toBe(900);
  });

  it("builds a claude-code command with a model", () => {
    const agent = buildAgentSpec("claude-code", {
      name: "baseline",
      timeoutS: 900,
      maxTurns: 5,
      model: "claude-opus-4",
      env: {},
      requiredSecrets: [],
    });
    expect(agent.command).toEqual([
      "claude",
      "-p",
      "--permission-mode",
      "acceptEdits",
      "--max-turns",
      "5",
      "--model",
      "claude-opus-4",
    ]);
  });

  it("builds a codex-cli command without a model", () => {
    const agent = buildAgentSpec("codex-cli", {
      name: "candidate",
      timeoutS: 900,
      env: {},
      requiredSecrets: [],
    });
    expect(agent.command).toEqual([
      "codex",
      "exec",
      "--skip-git-repo-check",
      "--sandbox",
      "workspace-write",
      "--ask-for-approval",
      "never",
      "-o",
      "{output_file}",
      "-",
    ]);
    expect(agent.input_mode).toBe("stdin");
    expect(agent.output_mode).toBe("file");
  });

  it("builds a codex-cli command with a model", () => {
    const agent = buildAgentSpec("codex-cli", {
      name: "candidate",
      timeoutS: 900,
      model: "gpt-5-codex",
      env: {},
      requiredSecrets: [],
    });
    expect(agent.command).toEqual([
      "codex",
      "exec",
      "--skip-git-repo-check",
      "--sandbox",
      "workspace-write",
      "--ask-for-approval",
      "never",
      "--model",
      "gpt-5-codex",
      "-o",
      "{output_file}",
      "-",
    ]);
  });

  it("builds an echo command", () => {
    const agent = buildAgentSpec("echo", { name: "echo", timeoutS: 10, env: {}, requiredSecrets: [] });
    expect(agent.command).toEqual(["cat"]);
    expect(agent.input_mode).toBe("stdin");
    expect(agent.output_mode).toBe("stdout");
  });

  it("keeps a custom line with spaces as a single argument (no shell splitting)", () => {
    const agent = buildAgentSpec("custom", {
      name: "custom",
      timeoutS: 60,
      customArgvLines: "python\nagent.py --flag with spaces\n",
      customInputMode: "file",
      customOutputMode: "directory",
      env: { FOO: "bar" },
      requiredSecrets: ["MICRO_EVAL_SECRET_KEY"],
    });
    expect(agent.command).toEqual(["python", "agent.py --flag with spaces"]);
    expect(agent.input_mode).toBe("file");
    expect(agent.output_mode).toBe("directory");
    expect(agent.env).toEqual({ FOO: "bar" });
    expect(agent.required_secrets).toEqual(["MICRO_EVAL_SECRET_KEY"]);
  });

  it("drops blank lines from custom argv", () => {
    const agent = buildAgentSpec("custom", {
      name: "custom",
      timeoutS: 60,
      customArgvLines: "one\n\n  \ntwo",
      env: {},
      requiredSecrets: [],
    });
    expect(agent.command).toEqual(["one", "two"]);
  });
});

describe("slugifyId", () => {
  it.each([
    ["Hello World!", "hello-world"],
    ["Claude Code Baseline", "claude-code-baseline"],
    ["already-fine", "already-fine"],
  ])("slugifies %j to %j", (input, expected) => {
    expect(slugifyId(input)).toBe(expected);
  });

  it.each([".", "..", "...", "", "!!!"])("returns empty string for %j", (input) => {
    expect(slugifyId(input)).toBe("");
  });
});

describe("parseEnvLines", () => {
  it("accepts A=b=c, keeping the value as b=c (split at first =)", () => {
    const { env, errors } = parseEnvLines("A=b=c");
    expect(env).toEqual({ A: "b=c" });
    expect(errors).toEqual([]);
  });

  it("rejects a key starting with a digit", () => {
    const { env, errors } = parseEnvLines("1bad=x");
    expect(env).toEqual({});
    expect(errors.length).toBe(1);
  });

  it("parses multiple valid lines and skips blanks", () => {
    const { env, errors } = parseEnvLines("FOO=bar\n\nBAZ=qux\n");
    expect(env).toEqual({ FOO: "bar", BAZ: "qux" });
    expect(errors).toEqual([]);
  });

  it("reports a line missing '='", () => {
    const { errors } = parseEnvLines("NOEQUALS");
    expect(errors.length).toBe(1);
  });
});

describe("detectPreset", () => {
  it("round-trips a claude-code spec", () => {
    const agent = buildAgentSpec("claude-code", {
      name: "baseline",
      timeoutS: 900,
      maxTurns: 7,
      model: "claude-opus-4",
      env: {},
      requiredSecrets: [],
    });
    expect(detectPreset(agent)).toEqual({ preset: "claude-code", model: "claude-opus-4", maxTurns: 7 });
  });

  it("detects codex-cli", () => {
    const agent = buildAgentSpec("codex-cli", { name: "c", timeoutS: 900, model: "gpt-5-codex", env: {}, requiredSecrets: [] });
    expect(detectPreset(agent)).toEqual({ preset: "codex-cli", model: "gpt-5-codex" });
  });

  it("detects echo", () => {
    expect(detectPreset({ command: ["cat"] })).toEqual({ preset: "echo" });
  });

  it("falls back to custom for anything else", () => {
    expect(detectPreset({ command: ["python", "agent.py"] })).toEqual({ preset: "custom" });
  });

  // R3 (round-6 review): a preset must only be detected when the argv
  // matches its exact shape end to end, not just argv[0] — otherwise a
  // hand-edited custom command starting with a preset's binary gets
  // silently rewritten to the preset's canonical shape on save.
  it("does not detect echo for a command that merely starts with 'cat'", () => {
    expect(detectPreset({ command: ["cat", "-n"] })).toEqual({ preset: "custom" });
  });

  it("does not detect claude-code for a command that merely starts with 'claude'", () => {
    expect(detectPreset({ command: ["claude", "--custom"] })).toEqual({ preset: "custom" });
  });

  it("round-trips a custom command with extra claude-like flags unchanged", () => {
    const command = ["claude", "--custom"];
    expect(detectPreset({ command })).toEqual({ preset: "custom" });
    // The form falls back to preserving the original argv verbatim for
    // "custom" — buildAgentSpec("custom", ...) with those lines must
    // reproduce the exact same command.
    const rebuilt = buildAgentSpec("custom", {
      name: "n",
      timeoutS: 60,
      customArgvLines: command.join("\n"),
      env: {},
      requiredSecrets: [],
    });
    expect(rebuilt.command).toEqual(command);
  });

  it("round-trips a custom command with extra 'cat' flags unchanged", () => {
    const command = ["cat", "-n"];
    expect(detectPreset({ command })).toEqual({ preset: "custom" });
    const rebuilt = buildAgentSpec("custom", {
      name: "n",
      timeoutS: 60,
      customArgvLines: command.join("\n"),
      env: {},
      requiredSecrets: [],
    });
    expect(rebuilt.command).toEqual(command);
  });

  it("still detects the exact codex-cli shape without a model", () => {
    expect(
      detectPreset({
        command: [
          "codex",
          "exec",
          "--skip-git-repo-check",
          "--sandbox",
          "workspace-write",
          "--ask-for-approval",
          "never",
          "-o",
          "{output_file}",
          "-",
        ],
      }),
    ).toEqual({ preset: "codex-cli" });
  });

  it("falls back to custom when codex-cli argv has an extra trailing flag", () => {
    expect(
      detectPreset({
        command: [
          "codex",
          "exec",
          "--skip-git-repo-check",
          "--sandbox",
          "workspace-write",
          "--ask-for-approval",
          "never",
          "-o",
          "{output_file}",
          "-",
          "--extra",
        ],
      }),
    ).toEqual({ preset: "custom" });
  });

  it("falls back to custom when claude-code argv has an extra trailing flag", () => {
    expect(
      detectPreset({
        command: ["claude", "-p", "--permission-mode", "acceptEdits", "--max-turns", "10", "--extra"],
      }),
    ).toEqual({ preset: "custom" });
  });
});
