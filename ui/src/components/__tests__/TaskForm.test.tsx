/**
 * GRO-552: TaskForm acceptance tests — adding contains/command expectations
 * produces the right body shape, selecting git_repo reveals path/ref,
 * an invalid id blocks submit, and the PUT carries the member header.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { TaskForm } from "../TaskForm";
import { TaskInputSchema, type TaskDraft } from "@/lib/project-schema";
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

const draftResponse = {
  project_name: "demo",
  description: "",
  configurations: [],
  configuration_errors: [],
  tasks: [],
  warnings: [],
};

describe("TaskForm", () => {
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

  it("adding a contains expectation and submitting produces the right body shape", async () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => draftResponse });
    vi.stubGlobal("fetch", fetchMock);

    const onSaved = vi.fn();
    render(<TaskForm workspaceId="ws-1" existing={null} onCancel={vi.fn()} onSaved={onSaved} />);

    fireEvent.change(screen.getByLabelText(/^name/i), { target: { value: "Hello Task" } });
    fireEvent.change(screen.getByLabelText(/^prompt/i), { target: { value: "hello" } });

    fireEvent.click(screen.getByRole("button", { name: /add expectation/i }));
    const containsValueInput = screen.getByPlaceholderText(/text the output must contain/i);
    fireEvent.change(containsValueInput, { target: { value: "hello" } });

    fireEvent.click(screen.getByRole("button", { name: /save task/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/workspaces/ws-1/project/tasks");
    expect(options.headers["X-Micro-Eval-Member"]).toBe("Alice");

    const body = JSON.parse(options.body);
    expect(() => TaskInputSchema.parse(body)).not.toThrow();
    expect(body.expectations).toEqual([
      { type: "contains", value: "hello", path: null, stream: "output", command: null, cwd: null, timeout_s: 30 },
    ]);

    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
  });

  it("adding a command expectation produces the right body shape", async () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => draftResponse });
    vi.stubGlobal("fetch", fetchMock);

    render(<TaskForm workspaceId="ws-1" existing={null} onCancel={vi.fn()} onSaved={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/^name/i), { target: { value: "Command Task" } });
    fireEvent.change(screen.getByLabelText(/^prompt/i), { target: { value: "run it" } });

    fireEvent.click(screen.getByRole("button", { name: /add expectation/i }));
    const typeSelect = screen.getAllByRole("combobox")[0];
    fireEvent.change(typeSelect, { target: { value: "command" } });

    const argvTextarea = screen.getByPlaceholderText(/one argument per line/i);
    fireEvent.change(argvTextarea, { target: { value: "test\n-f\noutput.txt" } });
    const cwdInput = screen.getByPlaceholderText(/workspace root; or \{output_dir\}/i);
    fireEvent.change(cwdInput, { target: { value: "{output_dir}" } });

    fireEvent.click(screen.getByRole("button", { name: /save task/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.expectations).toEqual([
      {
        type: "command",
        value: null,
        path: null,
        stream: "output",
        command: ["test", "-f", "output.txt"],
        cwd: "{output_dir}",
        timeout_s: 30,
      },
    ]);
  });

  it("choosing git_repo reveals path and ref fields", () => {
    render(<TaskForm workspaceId="ws-1" existing={null} onCancel={vi.fn()} onSaved={vi.fn()} />);

    expect(screen.queryByLabelText(/repo path/i)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /git repo/i }));

    expect(screen.getByLabelText(/repo path/i)).toBeTruthy();
    expect(screen.getByLabelText(/^ref$/i)).toBeTruthy();
  });

  it("blocks submit and shows a message when the id is invalid", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<TaskForm workspaceId="ws-1" existing={null} onCancel={vi.fn()} onSaved={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/^name/i), { target: { value: "Anything" } });
    fireEvent.change(screen.getByLabelText(/^id/i), { target: { value: "not a valid id" } });
    fireEvent.change(screen.getByLabelText(/^prompt/i), { target: { value: "hi" } });

    fireEvent.click(screen.getByRole("button", { name: /save task/i }));

    expect(await screen.findByText(/invalid task id/i)).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("editing an existing task keeps advanced workspace and conversational fields (F7 round trip)", async () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => draftResponse });
    vi.stubGlobal("fetch", fetchMock);

    const existing = {
      id: "hello",
      name: "Hello",
      description: "",
      input_payload: "hi",
      expected_output: null,
      rubric: null,
      expectations: [],
      workspace: {
        type: "git_repo",
        path: "/repo",
        ref: "main",
        files: [],
        setup: [["npm", "install"]],
        isolation_level: "os_policy",
        trust_level: "untrusted",
        network_policy: "none",
        fixtures: [{ path: "fixtures/a.json" }],
        toolchain: { runtime: "node20" },
      },
      business_impact_tier: 3,
      tags: [],
      revision_id: "deadbeef",
      scenario: "user reports a bug",
      expected_outcome: "agent fixes it",
      user_description: "terse user",
    } as unknown as TaskDraft;

    const onSaved = vi.fn();
    render(<TaskForm workspaceId="ws-1" existing={existing} onCancel={vi.fn()} onSaved={onSaved} />);

    expect(screen.getByText(/advanced workspace settings are kept as-is/i)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /save task/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/workspaces/ws-1/project/tasks");

    const body = JSON.parse(options.body);
    expect(() => TaskInputSchema.parse(body)).not.toThrow();
    expect(body.workspace.isolation_level).toBe("os_policy");
    expect(body.workspace.trust_level).toBe("untrusted");
    expect(body.workspace.network_policy).toBe("none");
    expect(body.workspace.fixtures).toEqual([{ path: "fixtures/a.json" }]);
    expect(body.workspace.toolchain).toEqual({ runtime: "node20" });
    expect(body.workspace.setup).toEqual([["npm", "install"]]);
    expect(body.scenario).toBe("user reports a bug");
    expect(body.expected_outcome).toBe("agent fixes it");
    expect(body.user_description).toBe("terse user");
    expect(body.revision_id).toBeUndefined();

    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
  });

  // N4: the id becomes the task file's name; changing it mid-edit would
  // orphan the old file instead of renaming it, so the field must be locked.
  it("locks the id field while editing an existing task", () => {
    const existing = {
      id: "hello",
      name: "Hello",
      description: "",
      input_payload: "hi",
      expected_output: null,
      rubric: null,
      expectations: [],
      workspace: { type: "blank", path: null, ref: null, files: [], setup: [] },
      business_impact_tier: 3,
      tags: [],
      revision_id: "deadbeef",
    } as unknown as TaskDraft;

    render(<TaskForm workspaceId="ws-1" existing={existing} onCancel={vi.fn()} onSaved={vi.fn()} />);

    const idInput = screen.getByLabelText(/^id/i) as HTMLInputElement;
    expect(idInput.readOnly).toBe(true);
    expect(screen.getByText(/id cannot change while editing/i)).toBeTruthy();
  });

  it("does not lock the id field when adding a new task", () => {
    render(<TaskForm workspaceId="ws-1" existing={null} onCancel={vi.fn()} onSaved={vi.fn()} />);

    const idInput = screen.getByLabelText(/^id/i) as HTMLInputElement;
    expect(idInput.readOnly).toBe(false);
    expect(screen.queryByText(/id cannot change while editing/i)).toBeNull();
  });

  // N5: a structured rubric ({text, dimensions}) must survive editing
  // unchanged; the basic form only edits free-text rubrics.
  it("keeps a structured rubric untouched and shows it read-only", async () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => draftResponse });
    vi.stubGlobal("fetch", fetchMock);

    const structuredRubric = { text: "score this", dimensions: ["correctness"] };
    const existing = {
      id: "hello",
      name: "Hello",
      description: "",
      input_payload: "hi",
      expected_output: null,
      rubric: structuredRubric,
      expectations: [],
      workspace: { type: "blank", path: null, ref: null, files: [], setup: [] },
      business_impact_tier: 3,
      tags: [],
      revision_id: "deadbeef",
    } as unknown as TaskDraft;

    render(<TaskForm workspaceId="ws-1" existing={existing} onCancel={vi.fn()} onSaved={vi.fn()} />);

    const rubricTextarea = screen.getByLabelText(/^rubric/i) as HTMLTextAreaElement;
    expect(rubricTextarea.value).toBe("score this");
    expect(rubricTextarea.disabled).toBe(true);
    expect(screen.getByText(/structured rubric; edit it in the task's yaml file/i)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /save task/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(() => TaskInputSchema.parse(body)).not.toThrow();
    expect(body.rubric).toEqual(structuredRubric);
  });

  // N6: a file_exists expectation normalised by the backend may only carry
  // its path in `value`; editing must not show an empty path field, and
  // submitting must send both `path` and `value`.
  it("recovers a file_exists path from `value` and submits both fields", async () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => draftResponse });
    vi.stubGlobal("fetch", fetchMock);

    const existing = {
      id: "hello",
      name: "Hello",
      description: "",
      input_payload: "hi",
      expected_output: null,
      rubric: null,
      expectations: [
        { type: "file_exists", value: "artifact.txt", path: null, stream: "output", command: null, cwd: null, timeout_s: 30 },
      ],
      workspace: { type: "blank", path: null, ref: null, files: [], setup: [] },
      business_impact_tier: 3,
      tags: [],
      revision_id: "deadbeef",
    } as unknown as TaskDraft;

    render(<TaskForm workspaceId="ws-1" existing={existing} onCancel={vi.fn()} onSaved={vi.fn()} />);

    const pathInput = screen.getByPlaceholderText(/path relative to the workspace/i) as HTMLInputElement;
    expect(pathInput.value).toBe("artifact.txt");

    fireEvent.click(screen.getByRole("button", { name: /save task/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.expectations).toEqual([
      { type: "file_exists", value: "artifact.txt", path: "artifact.txt", stream: "output", command: null, cwd: null, timeout_s: 30 },
    ]);
  });

  // Round-16 review: a `files` workspace may point at a directory via
  // `path`; the basic form must not null it out on save.
  it("keeps workspace.path for a files-type task it cannot edit", async () => {
    window.localStorage.setItem(MEMBER_NAME_KEY, "Alice");
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => draftResponse });
    vi.stubGlobal("fetch", fetchMock);

    const existing = {
      id: "copy",
      name: "Copy",
      description: "",
      input_payload: "hi",
      expected_output: null,
      rubric: null,
      expectations: [],
      workspace: { type: "files", path: "src", ref: null, files: [], setup: [] },
      business_impact_tier: 3,
      tags: [],
      revision_id: "deadbeef",
    } as unknown as TaskDraft;

    render(<TaskForm workspaceId="ws-1" existing={existing} onCancel={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByText(/is kept as-is; change it in the task's YAML file/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /save task/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.workspace.type).toBe("files");
    expect(body.workspace.path).toBe("src");
    expect(body.workspace.files).toEqual([]);
  });
});
