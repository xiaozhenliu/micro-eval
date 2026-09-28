/**
 * Task 1: member-identity.ts unit tests.
 *
 * Covers the single-source-of-truth localStorage helper used by journey
 * A4/A5 (member identity prompt + X-Micro-Eval-Member header attach).
 *
 * Note: vitest's jsdom environment glue only copies a fixed allowlist of
 * window properties onto the test global (see vitest/dist chunk
 * `populateGlobal`), and `localStorage` is not in that list because it is
 * defined via a prototype accessor rather than an own property. That means
 * `window.localStorage` is `undefined` by default under vitest+jsdom even
 * though it works in a real browser. We install a minimal in-memory
 * Storage-compatible stub for the duration of this suite so the module
 * under test (which correctly uses `window.localStorage`, matching real
 * browser behavior) can be exercised.
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { MEMBER_NAME_KEY, getMemberName, setMemberName } from "../member-identity";

function createMemoryStorage(): Storage {
  const store = new Map<string, string>();
  return {
    getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
    clear: () => {
      store.clear();
    },
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    get length() {
      return store.size;
    },
  };
}

describe("member-identity", () => {
  beforeEach(() => {
    // jsdom's own localStorage getter isn't reachable through vitest's
    // proxied global window, so install a fresh in-memory stand-in per test.
    Object.defineProperty(window, "localStorage", {
      value: createMemoryStorage(),
      configurable: true,
      writable: true,
    });
  });

  it("returns empty string when nothing is set", () => {
    expect(getMemberName()).toBe("");
  });

  it("writes then reads back the value", () => {
    setMemberName("Alice");
    expect(getMemberName()).toBe("Alice");
    expect(window.localStorage.getItem(MEMBER_NAME_KEY)).toBe("Alice");
  });

  it("trims leading/trailing whitespace on write", () => {
    setMemberName("  Bob  ");
    expect(getMemberName()).toBe("Bob");
    expect(window.localStorage.getItem(MEMBER_NAME_KEY)).toBe("Bob");
  });

  it("trims leading/trailing whitespace on read (defensive against manual edits)", () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "  Carol  ");
    expect(getMemberName()).toBe("Carol");
  });

  it("removes the key when writing an empty string", () => {
    setMemberName("Dave");
    expect(window.localStorage.getItem(MEMBER_NAME_KEY)).not.toBeNull();

    setMemberName("");
    expect(window.localStorage.getItem(MEMBER_NAME_KEY)).toBeNull();
    expect(getMemberName()).toBe("");
  });

  it("removes the key when writing a whitespace-only string", () => {
    setMemberName("Eve");
    setMemberName("   ");
    expect(window.localStorage.getItem(MEMBER_NAME_KEY)).toBeNull();
    expect(getMemberName()).toBe("");
  });

  describe("SSR safety (window undefined)", () => {
    let originalWindow: typeof window;

    beforeEach(() => {
      originalWindow = globalThis.window;
      // @ts-expect-error - simulate SSR environment where window is not defined
      delete globalThis.window;
    });

    afterEach(() => {
      globalThis.window = originalWindow;
    });

    it("getMemberName does not throw and returns empty string", () => {
      expect(() => getMemberName()).not.toThrow();
      expect(getMemberName()).toBe("");
    });

    it("setMemberName does not throw", () => {
      expect(() => setMemberName("Frank")).not.toThrow();
    });
  });
});
