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
 *
 * Round-6 review (R9/R10, 2026-09-12): the preview's plan_digest is echoed
 * back as `expected_plan_digest` on the enqueue POST, a 409 (configuration
 * changed since the preview) surfaces the server message and drops the
 * stale preview, and the cells formula only shows the `× reps` factor when
 * `repetitions_uniform` is true.
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
            repetitions_uniform: true,
            total_cells: 2,
            agent_commands: ["python agent-a.py", "python agent-b.py"],
            plan_digest: "hash-abc",
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
    expect(options.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(options.body)).toEqual({ expected_plan_digest: "hash-abc" });
  });

  it("shows the 'repetitions vary' phrasing instead of the × reps factor when repetitions_uniform is false", async () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        tasks: 2,
        configurations: 3,
        repetitions: 1,
        repetitions_uniform: false,
        total_cells: 5,
        agent_commands: [],
        plan_digest: "hash-xyz",
      }),
      text: async () => "",
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<RunEnqueueButton workspaceId="ws-1" />);
    fireEvent.click(screen.getByRole("button", { name: /enqueue run/i }));

    expect(await screen.findByText(/2 tasks × 3 configs = 5 cells \(repetitions vary per configuration\)/i)).toBeTruthy();
  });

  it("shows the server message and drops the stale preview on a 409 (configuration changed)", async () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");

    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/workspaces/ws-1/plan-summary") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            tasks: 1,
            configurations: 1,
            repetitions: 1,
            repetitions_uniform: true,
            total_cells: 1,
            agent_commands: [],
            plan_digest: "stale-hash",
          }),
          text: async () => "",
        });
      }
      return Promise.resolve({
        ok: false,
        status: 409,
        json: async () => ({ error: "configuration changed since the preview; review the new preview" }),
        text: async () => "",
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<RunEnqueueButton workspaceId="ws-1" />);
    fireEvent.click(screen.getByRole("button", { name: /enqueue run/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    fireEvent.click(await screen.findByRole("button", { name: /confirm & enqueue/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    expect(await screen.findByText(/configuration changed since the preview/i)).toBeTruthy();
    // The stale preview card is gone — the button is back to its initial state.
    expect(screen.queryByText(/run preview/i)).toBeNull();
    expect(screen.getByRole("button", { name: /enqueue run/i })).toBeTruthy();
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

  it("still surfaces the invalid-ref hint when the degraded enqueue is refused by the backend", async () => {
    // Round-1 coverage: a preview that failed without a detail degrades and
    // lets the member enqueue; the backend still validates the ref and the
    // refusal carries the fixed hint.
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/workspaces/ws-1/plan-summary") {
        return Promise.resolve({ ok: false, status: 502, json: async () => ({}), text: async () => "" });
      }
      return Promise.resolve({
        ok: false,
        status: 502,
        json: async () => ({
          error: "failed to build run plan",
          detail: "[task=t] git ref cannot be resolved to a commit",
          reason: "invalid_git_ref",
          hint: "Use a branch, tag, or commit SHA that exists in the server repository and resolves to a commit. Correct the ref or fetch the required commit, then preview again.",
        }),
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<RunEnqueueButton workspaceId="ws-1" />);
    fireEvent.click(screen.getByRole("button", { name: /enqueue run/i }));
    expect(await screen.findByText(/could not load plan preview/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /confirm & enqueue/i }));

    expect(await screen.findByText(/then preview again/)).toBeTruthy();
    expect(await screen.findByText(/\[task=t\] git ref cannot be resolved to a commit/)).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("shows source preflight detail and blocks confirmation when preview is refused", async () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => ({ error: "failed to build plan summary", detail: "task t: workspace source not found: missing" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<RunEnqueueButton workspaceId="ws-1" />);
    fireEvent.click(screen.getByRole("button", { name: /enqueue run/i }));

    expect(await screen.findByText("task t: workspace source not found: missing")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /confirm & enqueue/i })).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("appends the fixed invalid-git-ref hint when the preview refusal carries the reason", async () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => ({
        error: "failed to build plan summary",
        detail: "[task=t] git ref cannot be resolved to a commit",
        reason: "invalid_git_ref",
        hint: "Use a branch, tag, or commit SHA that exists in the server repository and resolves to a commit. Correct the ref or fetch the required commit, then preview again.",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<RunEnqueueButton workspaceId="ws-1" />);
    fireEvent.click(screen.getByRole("button", { name: /enqueue run/i }));

    expect(await screen.findByText(/\[task=t\] git ref cannot be resolved to a commit/)).toBeTruthy();
    expect(await screen.findByText(/Use a branch, tag, or commit SHA/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /confirm & enqueue/i })).toBeNull();
  });

  it("ignores a hint that does not belong to the known refusal reason", async () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => ({
        error: "failed to build plan summary",
        detail: "task t: workspace source not found: missing",
        reason: "something_else",
        hint: "arbitrary backend hint",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<RunEnqueueButton workspaceId="ws-1" />);
    fireEvent.click(screen.getByRole("button", { name: /enqueue run/i }));

    expect(await screen.findByText("task t: workspace source not found: missing")).toBeTruthy();
    expect(screen.queryByText(/arbitrary backend hint/)).toBeNull();
  });

  it("appends the fixed hint when the enqueue refusal carries the invalid-git-ref reason", async () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/workspaces/ws-1/plan-summary") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            tasks: 1,
            configurations: 1,
            repetitions: 1,
            repetitions_uniform: true,
            total_cells: 1,
            agent_commands: [],
            plan_digest: "hash-abc",
          }),
        });
      }
      return Promise.resolve({
        ok: false,
        status: 502,
        json: async () => ({
          error: "failed to build run plan",
          detail: "[task=t] git ref cannot be resolved to a commit",
          reason: "invalid_git_ref",
          hint: "Use a branch, tag, or commit SHA that exists in the server repository and resolves to a commit. Correct the ref or fetch the required commit, then preview again.",
        }),
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<RunEnqueueButton workspaceId="ws-1" />);
    fireEvent.click(screen.getByRole("button", { name: /enqueue run/i }));
    fireEvent.click(await screen.findByRole("button", { name: /confirm & enqueue/i }));

    expect(await screen.findByText(/then preview again/)).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("shows source preflight detail when enqueue is refused after a preview", async () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/workspaces/ws-1/plan-summary") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            tasks: 1,
            configurations: 1,
            repetitions: 1,
            repetitions_uniform: true,
            total_cells: 1,
            agent_commands: [],
            plan_digest: "hash-abc",
          }),
        });
      }
      return Promise.resolve({
        ok: false,
        status: 502,
        json: async () => ({ error: "failed to build run plan", detail: "task t: workspace source not found: missing" }),
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<RunEnqueueButton workspaceId="ws-1" />);
    fireEvent.click(screen.getByRole("button", { name: /enqueue run/i }));
    fireEvent.click(await screen.findByRole("button", { name: /confirm & enqueue/i }));

    expect(await screen.findByText("task t: workspace source not found: missing")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
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

  it("disables the button and shows the reason when disabledReason is set", () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<RunEnqueueButton workspaceId="ws-1" disabledReason="Add at least one configuration and one task first" />);

    const button = screen.getByRole("button", { name: /enqueue run/i });
    expect(button).toHaveProperty("disabled", true);
    expect(screen.getByText(/add at least one configuration and one task first/i)).toBeTruthy();

    fireEvent.click(button);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
