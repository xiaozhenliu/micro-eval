import { execFileSync } from "node:child_process";
import { NextResponse } from "next/server";
import { z } from "zod";
import { isServerMode, getServerDataRoot } from "@/lib/server-mode";
import { listWorkspaces } from "@/lib/workspace-api";
import { validateWriteRequest, uvBin, TEMPLATE_ID_RE, sanitizeErrorDetail } from "@/lib/server-validation";

const CreateWorkspaceSchema = z.object({
  name: z.string().min(1).max(120),
  description: z.string().max(500).default(""),
  template_id: z.string().regex(TEMPLATE_ID_RE, "invalid template_id").nullable().default(null),
});

export async function GET() {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });
  const workspaces = listWorkspaces();
  return NextResponse.json(workspaces);
}

export async function POST(request: Request) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const validation = validateWriteRequest(request);
  if (validation instanceof NextResponse) return validation;
  const { member } = validation;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  let input: z.infer<typeof CreateWorkspaceSchema>;
  try {
    input = CreateWorkspaceSchema.parse(body);
  } catch (err) {
    return NextResponse.json({ error: "invalid request body", detail: String(err) }, { status: 400 });
  }

  const args = [
    "run", "micro-eval", "workspace", "create",
    "--name", input.name,
    "--owner", member,
  ];
  if (input.description) args.push("--description", input.description);
  if (input.template_id) args.push("--template", input.template_id);

  try {
    const stdout = execFileSync(uvBin(), args, {
      encoding: "utf-8",
      cwd: getServerDataRoot(),
      timeout: 30_000,
    });
    return NextResponse.json(JSON.parse(stdout), { status: 201 });
  } catch (err) {
    const detail = sanitizeErrorDetail(err instanceof Error ? err.message : String(err));
    return NextResponse.json({ error: "workspace creation failed", detail }, { status: 502 });
  }
}
