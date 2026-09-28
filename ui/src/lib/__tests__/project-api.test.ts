// @vitest-environment node
/**
 * N9: `uv run` may print its own warnings (e.g. a stale-lockfile notice) on
 * stderr before the CLI's structured `{"error", "kind"}` JSON. extractCliError
 * must scan stderr from the end and use the last line that parses as that
 * shape, not assume the whole of stderr (or its first line) is the JSON
 * payload. This is exercised indirectly through readProjectDraft since
 * extractCliError itself is not exported.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

const execFileSyncMock = vi.fn();

vi.mock("node:child_process", () => ({
  execFileSync: (...args: unknown[]) => execFileSyncMock(...args),
}));

import { readProjectDraft, ProjectApiError } from "../project-api";

function mockCliFailure(stderr: string, status: number | null = 1): void {
  execFileSyncMock.mockImplementation(() => {
    const err = new Error("command failed") as Error & { stderr: string; status: number | null };
    err.stderr = stderr;
    err.status = status;
    throw err;
  });
}

describe("N9: extractCliError scans stderr from the end for the last JSON line", () => {
  beforeEach(() => {
    execFileSyncMock.mockReset();
  });

  it("uses the last JSON line's error/kind when a warning line precedes it", () => {
    mockCliFailure('warning: `uv.lock` is out of date\n{"error": "project not found", "kind": "validation"}');

    expect.assertions(3);
    try {
      readProjectDraft("/tmp/does-not-matter");
    } catch (err) {
      expect(err).toBeInstanceOf(ProjectApiError);
      expect((err as ProjectApiError).message).toBe("project not found");
      expect((err as ProjectApiError).status).toBe(400);
    }
  });

  it("falls back to the fixed message with status 502 when stderr has no JSON line at all", () => {
    mockCliFailure("Traceback (most recent call last):\n  some internal python garbage\n");

    expect.assertions(3);
    try {
      readProjectDraft("/tmp/does-not-matter");
    } catch (err) {
      expect(err).toBeInstanceOf(ProjectApiError);
      expect((err as ProjectApiError).status).toBe(502);
      expect((err as ProjectApiError).message).toMatch(/^config command failed \(exit/);
    }
  });
});
