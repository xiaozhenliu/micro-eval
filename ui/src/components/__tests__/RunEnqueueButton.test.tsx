/**
 * Task 3/14: RunEnqueueButton acceptance tests.
 *
 * Covers journey A5 — the button reads member identity from localStorage
 * (via lib/member-identity), attaches it as X-Micro-Eval-Member on enqueue,
 * and blocks the request with an inline prompt when no name is set yet.
 *
 * Covers journey C14 — clicking "Enqueue Run" first fetches a plan-summary
 * preview and shows a confirmation card; the actual enqueue POST only fires
 * after "Confirm & Enqueue". A failed/absent plan-summary degrades to a
 * warning card that still allows enqueue.
 */

import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
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
    cleanup();
    vi.restoreAllMocks();
  });

  it("sends X-Micro-Eval-Member header with the stored member name after confirm", async () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");

    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/workspaces/ws-1/plan-summary") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            tasks: 1,
            configurations: 2,
            repetitions: 1,
            total_cells: 2,
            agent_commands: ["python agent-a.py", "python agent-b.py"],
          }),
          text: async () => "",
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ job_id: "j1" }),
        text: async () => "",
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<RunEnqueueButton workspaceId="ws-1" />);

    const button = screen.getByRole("button", { name: /enqueue run/i });
    fireEvent.click(button);

    // Plan summary is fetched and rendered as a preview card first.
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/workspaces/ws-1/plan-summary");
    expect(await screen.findByText(/1 task × 2 configs × 1 rep = 2 cells/i)).toBeTruthy();

    const confirmButton = screen.getByRole("button", { name: /confirm & enqueue/i });
    fireEvent.click(confirmButton);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const [url, options] = fetchMock.mock.calls[1];
    expect(url).toBe("/api/workspaces/ws-1/runs/enqueue");
    expect(options.method).toBe("POST");
    expect(options.headers["X-Micro-Eval-Member"]).toBe("Alice");
  });

  it("degrades to a warning card and still allows enqueue when plan-summary fails", async () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");

    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/workspaces/ws-1/plan-summary") {
        return Promise.resolve({ ok: false, status: 502, json: async () => ({}), text: async () => "" });
      }
      return Promise.resolve({ ok: true, json: async () => ({ job_id: "j1" }), text: async () => "" });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<RunEnqueueButton workspaceId="ws-1" />);

    fireEvent.click(screen.getByRole("button", { name: /enqueue run/i }));

    expect(await screen.findByText(/could not load plan preview/i)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /confirm & enqueue/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[1][0]).toBe("/api/workspaces/ws-1/runs/enqueue");
  });

  it("cancels the confirmation card without enqueueing", async () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        tasks: 1,
        configurations: 1,
        repetitions: 1,
        total_cells: 1,
        agent_commands: [],
      }),
      text: async () => "",
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<RunEnqueueButton workspaceId="ws-1" />);

    fireEvent.click(screen.getByRole("button", { name: /enqueue run/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    fireEvent.click(await screen.findByRole("button", { name: /cancel/i }));

    expect(screen.queryByText(/run preview/i)).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
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
