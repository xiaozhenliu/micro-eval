/**
 * GRO-551: ConfigurationForm acceptance tests — command preview reacts to
 * preset selection, a valid submit PUTs a body that passes
 * ConfigurationInputSchema with the member header attached, and an invalid
 * id blocks submission with a visible message.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { ConfigurationForm } from "../ConfigurationForm";
import { ConfigurationInputSchema, type ConfigurationDraft } from "@/lib/project-schema";
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
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

describe("ConfigurationForm", () => {
  beforeEach(() => {
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

  it("updates the command preview when selecting Claude Code and entering a model", () => {
    render(<ConfigurationForm workspaceId="ws-1" existing={null} onCancel={vi.fn()} onSaved={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/agent preset/i), { target: { value: "claude-code" } });
    expect(screen.getByText(/claude -p --permission-mode acceptEdits --max-turns 10/)).toBeTruthy();

    fireEvent.change(screen.getByLabelText(/^model$/i), { target: { value: "claude-opus-4" } });
    expect(screen.getByText(/--model claude-opus-4/)).toBeTruthy();
  });

  it("submits a PUT with the member header and a body that passes ConfigurationInputSchema", async () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        project_name: "demo",
        description: "",
        configurations: [],
        configuration_errors: [],
        tasks: [],
        warnings: [],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const onSaved = vi.fn();
    render(<ConfigurationForm workspaceId="ws-1" existing={null} onCancel={vi.fn()} onSaved={onSaved} />);

    fireEvent.change(screen.getByLabelText(/^name/i), { target: { value: "Echo Baseline" } });
    fireEvent.change(screen.getByLabelText(/agent preset/i), { target: { value: "echo" } });

    fireEvent.click(screen.getByRole("button", { name: /save configuration/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/workspaces/ws-1/project/configurations");
    expect(options.method).toBe("PUT");
    expect(options.headers["X-Micro-Eval-Member"]).toBe("Alice");
    expect(options.headers["Content-Type"]).toBe("application/json");

    const body = JSON.parse(options.body);
    expect(body.id).toBe("echo-baseline");
    expect(() => ConfigurationInputSchema.parse(body)).not.toThrow();
    expect(body.agent.command).toEqual(["cat"]);

    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
  });

  it("blocks submit and shows a message when the id is invalid", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<ConfigurationForm workspaceId="ws-1" existing={null} onCancel={vi.fn()} onSaved={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/^name/i), { target: { value: "Anything" } });
    fireEvent.change(screen.getByLabelText(/^id/i), { target: { value: "not a valid id" } });

    fireEvent.click(screen.getByRole("button", { name: /save configuration/i }));

    expect(await screen.findByText(/invalid configuration id/i)).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  // R2 (round-6 review): editing a configuration must not change its id —
  // the id becomes the eval.yaml key, so renaming it mid-edit would create a
  // duplicate entry instead of renaming the existing one.
  it("locks the id field while editing an existing configuration", () => {
    const existing = {
      id: "claude-baseline",
      name: "Claude Baseline",
      agent: {
        name: "agent",
        command: ["claude", "-p", "--permission-mode", "acceptEdits", "--max-turns", "10"],
        input_mode: "stdin",
        output_mode: "stdout",
        timeout_s: 900,
        env: {},
        required_secrets: [],
      },
      repetitions: 1,
      role: null,
      skills_profile: {},
      parameters: {},
    } as unknown as ConfigurationDraft;

    render(<ConfigurationForm workspaceId="ws-1" existing={existing} onCancel={vi.fn()} onSaved={vi.fn()} />);

    const idInput = screen.getByLabelText(/^id/i) as HTMLInputElement;
    expect(idInput.readOnly).toBe(true);
    expect(screen.getByText(/id cannot change while editing/i)).toBeTruthy();
  });

  it("does not lock the id field when adding a new configuration", () => {
    render(<ConfigurationForm workspaceId="ws-1" existing={null} onCancel={vi.fn()} onSaved={vi.fn()} />);

    const idInput = screen.getByLabelText(/^id/i) as HTMLInputElement;
    expect(idInput.readOnly).toBe(false);
    expect(screen.queryByText(/id cannot change while editing/i)).toBeNull();
  });
});
