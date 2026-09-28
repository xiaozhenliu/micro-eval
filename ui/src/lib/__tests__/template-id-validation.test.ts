/**
 * Regression tests for template_id path-traversal hardening (GRO-172 / H1).
 *
 * `TEMPLATE_ID_RE` is the single source of truth shared by `safeTemplateId`
 * (templates/[id] route + page) and the POST /api/workspaces zod schema. It
 * must reject any id that could escape the templates root once handed to the
 * Python side as `--template <id>`.
 */

import { describe, it, expect } from "vitest";
import { z } from "zod";
import { TEMPLATE_ID_RE, safeTemplateId } from "../server-validation";

// Mirror of the schema field guarding POST /api/workspaces (route.ts).
const templateIdField = z
  .string()
  .regex(TEMPLATE_ID_RE, "invalid template_id")
  .nullable()
  .default(null);

const VALID = ["tpl-a", "tpl_1", "a.b.c", "A1", "x".repeat(64), "1.0.0"];

const REJECTED = [
  "..",
  ".",
  "...",
  "/etc",
  "../../../etc/ssh",
  "../evil",
  "a/b",
  "", // empty
  "x".repeat(65), // too long
  "tpl a", // space
  "tpl$", // disallowed symbol
  "tpl\n", // trailing newline must not slip past the anchor
  "évil", // non-ASCII
];

describe("TEMPLATE_ID_RE / safeTemplateId", () => {
  it.each(VALID)("accepts valid id %j", (id) => {
    expect(TEMPLATE_ID_RE.test(id)).toBe(true);
    expect(safeTemplateId(id)).toBe(id);
  });

  it.each(REJECTED)("rejects traversal/malformed id %j", (id) => {
    expect(TEMPLATE_ID_RE.test(id)).toBe(false);
    expect(safeTemplateId(id)).toBeNull();
  });
});

describe("POST /api/workspaces template_id schema field", () => {
  it("accepts a well-formed template_id", () => {
    expect(templateIdField.parse("tpl-a")).toBe("tpl-a");
  });

  it("accepts null / omitted template_id", () => {
    expect(templateIdField.parse(null)).toBeNull();
    expect(templateIdField.parse(undefined)).toBeNull();
  });

  it.each(["..", "/etc", "../../../etc/ssh", "a/b"])(
    "rejects traversal payload %j",
    (id) => {
      expect(() => templateIdField.parse(id)).toThrow();
    },
  );
});
