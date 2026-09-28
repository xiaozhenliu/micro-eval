/**
 * Round-4 review: when eval.yaml could not be read the Advanced editor must
 * not offer a Save button that would overwrite the file with an empty body.
 */

import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { ConfigEditor } from "../ConfigEditor";

describe("ConfigEditor", () => {
  afterEach(() => cleanup());

  it("disables Save and explains why when the read failed", () => {
    render(<ConfigEditor workspaceId="ws-1" initialContent="" readFailed />);
    const save = screen.getByRole("button", { name: "Save" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    expect(screen.getByText(/saving is disabled/)).toBeTruthy();
  });

  it("keeps Save enabled and shows the redaction note when content is redacted", () => {
    render(<ConfigEditor workspaceId="ws-1" initialContent="project_name: x\n" redacted />);
    const save = screen.getByRole("button", { name: "Save" }) as HTMLButtonElement;
    expect(save.disabled).toBe(false);
    expect(screen.getByText(/\[REDACTED:NAME\]/)).toBeTruthy();
  });
});
