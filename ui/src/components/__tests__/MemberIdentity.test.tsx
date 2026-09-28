/**
 * Task 13: MemberIdentity acceptance tests.
 *
 * Covers C11 — the widget reads the stored member name via lib/member-identity,
 * shows a fallback prompt when unset, and lets the user edit + persist a new
 * name through setMemberName (never touching localStorage directly).
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { MemberIdentity } from "../MemberIdentity";
import { MEMBER_NAME_KEY } from "@/lib/member-identity";

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

describe("MemberIdentity", () => {
  beforeEach(() => {
    // jsdom's localStorage isn't reachable through vitest's proxied window;
    // install a fresh in-memory stand-in per test (see member-identity.test.ts).
    Object.defineProperty(window, "localStorage", {
      value: createMemoryStorage(),
      configurable: true,
      writable: true,
    });
  });

  afterEach(() => {
    // vitest.config.ts runs with globals: false and no setupFiles, so RTL's
    // automatic cleanup-after-each isn't wired up — do it explicitly to avoid
    // leaking rendered DOM (and duplicate role matches) across tests.
    cleanup();
    window.localStorage.clear();
  });

  it("shows the stored member name on mount", async () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");

    render(<MemberIdentity />);

    expect(await screen.findByRole("button", { name: "Alice" })).toBeTruthy();
  });

  it("shows a fallback prompt when no name is set", async () => {
    render(<MemberIdentity />);

    expect(await screen.findByRole("button", { name: /set your name/i })).toBeTruthy();
  });

  it("lets the user edit and save a new name via setMemberName", async () => {
    render(<MemberIdentity />);

    const trigger = await screen.findByRole("button", { name: /set your name/i });
    fireEvent.click(trigger);

    const input = screen.getByPlaceholderText("Your name");
    fireEvent.change(input, { target: { value: "Bob" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Bob" })).toBeTruthy());
    expect(window.localStorage.getItem(MEMBER_NAME_KEY)).toBe("Bob");
  });

  it("saves on Enter key press", async () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");

    render(<MemberIdentity />);

    fireEvent.click(await screen.findByRole("button", { name: "Alice" }));
    const input = screen.getByPlaceholderText("Your name");
    fireEvent.change(input, { target: { value: "Carol" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => expect(screen.getByRole("button", { name: "Carol" })).toBeTruthy());
    expect(window.localStorage.getItem(MEMBER_NAME_KEY)).toBe("Carol");
  });

  it("discards edits on cancel", async () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");

    render(<MemberIdentity />);

    fireEvent.click(await screen.findByRole("button", { name: "Alice" }));
    const input = screen.getByPlaceholderText("Your name");
    fireEvent.change(input, { target: { value: "Discarded" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(await screen.findByRole("button", { name: "Alice" })).toBeTruthy();
    expect(window.localStorage.getItem(MEMBER_NAME_KEY)).toBe("Alice");
  });
});
