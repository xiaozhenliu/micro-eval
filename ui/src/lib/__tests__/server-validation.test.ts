/**
 * Unit tests for validateWriteRequest (GRO-174 / audit M2).
 *
 * Covers CSRF layer 1 (Content-Type enforcement) and layer 2 (custom header).
 */

import { describe, it, expect } from "vitest";
import { NextResponse } from "next/server";
import { validateWriteRequest } from "../server-validation";

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
