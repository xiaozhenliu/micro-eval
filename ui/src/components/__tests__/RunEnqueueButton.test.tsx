/**
 * Task 3: RunEnqueueButton acceptance tests.
 *
 * Covers journey A5 — the button reads member identity from localStorage
 * (via lib/member-identity), attaches it as X-Micro-Eval-Member on enqueue,
 * and blocks the request with an inline prompt when no name is set yet.
 */

import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { RunEnqueueButton } from "../RunEnqueueButton";
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

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    refresh: vi.fn(),
  }),
}));

describe("RunEnqueueButton", () => {
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
    vi.restoreAllMocks();
  });

  it("sends X-Micro-Eval-Member header with the stored member name on success", async () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ job_id: "j1" }),
      text: async () => "",
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<RunEnqueueButton workspaceId="ws-1" />);

    const button = screen.getByRole("button", { name: /enqueue run/i });
    fireEvent.click(button);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/workspaces/ws-1/runs/enqueue");
    expect(options.method).toBe("POST");
    expect(options.headers["X-Micro-Eval-Member"]).toBe("Alice");
  });

  it("shows a hint and does not call fetch when no member name is set", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<RunEnqueueButton workspaceId="ws-1" />);

    const button = screen.getByRole("button", { name: /enqueue run/i });
    fireEvent.click(button);

    expect(await screen.findByText(/set your name first/i)).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
