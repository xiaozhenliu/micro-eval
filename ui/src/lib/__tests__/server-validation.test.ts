/**
 * Unit tests for validateWriteRequest (GRO-174 / audit M2) and
 * redactDeclaredSecrets (round-6 review, R1).
 *
 * Covers CSRF layer 1 (Content-Type enforcement) and layer 2 (custom header).
 */

import { describe, it, expect } from "vitest";
import { NextResponse } from "next/server";
import { validateWriteRequest, redactDeclaredSecrets, sanitizePlanBuildDetail } from "../server-validation";

function req(headers: Record<string, string>): Request {
  return new Request("http://localhost:3000/api/workspaces", {
    method: "POST",
    headers,
  });
}

describe("validateWriteRequest", () => {
  describe("CSRF layer 1: Content-Type enforcement", () => {
    it("rejects when Content-Type header is missing", () => {
      const result = validateWriteRequest(
        req({ "x-micro-eval-member": "alice" }),
      );
      expect(result).toBeInstanceOf(NextResponse);
      expect((result as NextResponse).status).toBe(400);
    });

    it("rejects when Content-Type is not application/json", () => {
      const result = validateWriteRequest(
        req({
          "content-type": "text/plain",
          "x-micro-eval-member": "alice",
        }),
      );
      expect(result).toBeInstanceOf(NextResponse);
      expect((result as NextResponse).status).toBe(400);
    });

    it("accepts application/json", () => {
      const result = validateWriteRequest(
        req({
          "content-type": "application/json",
          "x-micro-eval-member": "alice",
        }),
      );
      expect(result).not.toBeInstanceOf(NextResponse);
      expect((result as { member: string }).member).toBe("alice");
    });

    it("accepts application/json with charset suffix", () => {
      const result = validateWriteRequest(
        req({
          "content-type": "application/json; charset=utf-8",
          "x-micro-eval-member": "bob",
        }),
      );
      expect(result).not.toBeInstanceOf(NextResponse);
    });

    it("rejects media type smuggling via parameter injection", () => {
      const result = validateWriteRequest(
        req({
          "content-type": 'text/plain; foo="application/json"',
          "x-micro-eval-member": "alice",
        }),
      );
      expect(result).toBeInstanceOf(NextResponse);
      expect((result as NextResponse).status).toBe(400);
    });

    it("rejects application/x-www-form-urlencoded (simple request type)", () => {
      const result = validateWriteRequest(
        req({
          "content-type": "application/x-www-form-urlencoded",
          "x-micro-eval-member": "alice",
        }),
      );
      expect(result).toBeInstanceOf(NextResponse);
      expect((result as NextResponse).status).toBe(400);
    });
  });

  describe("CSRF layer 2: X-Micro-Eval-Member header", () => {
    it("rejects when member header is missing", () => {
      const result = validateWriteRequest(
        req({ "content-type": "application/json" }),
      );
      expect(result).toBeInstanceOf(NextResponse);
      expect((result as NextResponse).status).toBe(400);
    });

    it("rejects when member header has invalid characters", () => {
      const result = validateWriteRequest(
        req({
          "content-type": "application/json",
          "x-micro-eval-member": "alice<script>",
        }),
      );
      expect(result).toBeInstanceOf(NextResponse);
    });
  });
});

describe("redactDeclaredSecrets (round-6 review R1)", () => {
  it("masks a short (< 4 char) secret embedded inside a longer string", () => {
    const env = { ...process.env, MICRO_EVAL_SECRET_PIN: "42" };
    const text = "Authorization: Bearer 42-rest-of-token";
    expect(redactDeclaredSecrets(text, env)).toBe("Authorization: Bearer [REDACTED:MICRO_EVAL_SECRET_PIN]-rest-of-token");
  });

  it("masks a short secret glued directly to surrounding word characters", () => {
    const env = { ...process.env, MICRO_EVAL_SECRET_CODE: "ab" };
    // Previously the whole-word rule for short secrets meant "xaby" would not
    // be redacted at all because "ab" is not a standalone word here.
    expect(redactDeclaredSecrets("xaby", env)).toBe("x[REDACTED:MICRO_EVAL_SECRET_CODE]y");
  });

  it("still masks an exact whole-string match at any length", () => {
    const env = { ...process.env, MICRO_EVAL_SECRET_PIN: "7" };
    expect(redactDeclaredSecrets("7", env)).toBe("[REDACTED:MICRO_EVAL_SECRET_PIN]");
  });

  it("masks a long secret as a substring regardless of surrounding characters", () => {
    const env = { ...process.env, MICRO_EVAL_SECRET_API_KEY: "sk-live-secret-value-123456" };
    const text = "curl -H 'Bearer sk-live-secret-value-123456'";
    expect(redactDeclaredSecrets(text, env)).toBe("curl -H 'Bearer [REDACTED:MICRO_EVAL_SECRET_API_KEY]'");
  });

  it("masks every occurrence when the secret appears more than once", () => {
    const env = { ...process.env, MICRO_EVAL_SECRET_PIN: "42" };
    expect(redactDeclaredSecrets("42 and 42 again", env)).toBe(
      "[REDACTED:MICRO_EVAL_SECRET_PIN] and [REDACTED:MICRO_EVAL_SECRET_PIN] again",
    );
  });

  it("leaves text untouched when no declared secret is present", () => {
    const env = { ...process.env, MICRO_EVAL_SECRET_PIN: "42" };
    expect(redactDeclaredSecrets("nothing sensitive here", env)).toBe("nothing sensitive here");
  });
});

describe("sanitizePlanBuildDetail", () => {
  it("keeps a nested relative source path and its task id", () => {
    expect(sanitizePlanBuildDetail("task t: workspace source not found: src/missing.py", { NODE_ENV: "test" })).toBe(
      "task t: workspace source not found: src/missing.py",
    );
  });

  it("falls back to absolute path masking for unexpected detail", () => {
    expect(sanitizePlanBuildDetail("task t: workspace source not found: /private/secret", { NODE_ENV: "test" })).toBe(
      "task t: workspace source not found: <path>",
    );
  });

  it("redacts a declared secret before shortening the detail", () => {
    const detail = "task t: workspace source not found: src/sk-secret/missing.py";
    expect(sanitizePlanBuildDetail(detail, { NODE_ENV: "test", MICRO_EVAL_SECRET_TOKEN: "sk-secret" })).toBe(
      "task t: workspace source not found: src/[REDACTED:MICRO_EVAL_SECRET_TOKEN]/missing.py",
    );
  });
});
