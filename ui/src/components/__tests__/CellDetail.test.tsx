/**
 * C13: Plain-language failure explanation per cell.
 *
 * Only the pure mapping function `cellExplanation` is tested directly —
 * CellDetail itself has heavy Run/artifact/evidence/trace dependencies that
 * aren't relevant to this mapping logic.
 */

import { describe, it, expect } from "vitest";
import { cellExplanation } from "../CellDetail";

describe("cellExplanation", () => {
  it("explains a timeout", () => {
    expect(cellExplanation({ status: "timeout" })).toContain("timeout");
  });

  it("explains an error status with exit code", () => {
    expect(cellExplanation({ status: "error", exit_code: 1 })).toContain("exit code 1");
  });

  it("explains a non-zero exit code even when status is not 'error'", () => {
    expect(cellExplanation({ status: "fail", exit_code: 2 })).toContain("exit code 2");
  });

  it("falls back to 'unknown' when exit code is missing on an error status", () => {
    expect(cellExplanation({ status: "error", exit_code: null })).toContain("exit code unknown");
  });

  it("explains a validation failure when the process exited cleanly", () => {
    expect(cellExplanation({ status: "fail", exit_code: 0 })).toContain("validation");
  });

  it("explains a validation failure when exit code is absent", () => {
    expect(cellExplanation({ status: "fail" })).toContain("validation");
  });

  it("returns null for a passing cell", () => {
    expect(cellExplanation({ status: "pass", exit_code: 0 })).toBeNull();
  });
});
