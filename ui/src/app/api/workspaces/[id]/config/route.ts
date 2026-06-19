import path from "node:path";
import fs from "node:fs";
import { NextResponse } from "next/server";
import { isServerMode } from "@/lib/server-mode";
import { resolveWorkspacePath } from "@/lib/workspace-api";
import { validateWriteRequest } from "@/lib/server-validation";

interface RouteContext {
  params: Promise<{ id: string }>;
}

// Maximum allowed eval.yaml size (256 KiB)
const MAX_YAML_BYTES = 256 * 1024;

export async function GET(_request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const { id } = await context.params;
  const wsPath = resolveWorkspacePath(id);
  if (!wsPath) return NextResponse.json({ error: "workspace not found" }, { status: 404 });

  const evalYamlPath = path.join(wsPath, "eval.yaml");
  if (!fs.existsSync(evalYamlPath)) {
    return NextResponse.json({ error: "eval.yaml not found" }, { status: 404 });
  }

  const content = fs.readFileSync(evalYamlPath, "utf-8");
  return new Response(content, {
    headers: { "content-type": "text/plain; charset=utf-8" },
  });
}

export async function PUT(request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const validation = validateWriteRequest(request);
  if (validation instanceof NextResponse) return validation;

  const { id } = await context.params;
  const wsPath = resolveWorkspacePath(id);
  if (!wsPath) return NextResponse.json({ error: "workspace not found" }, { status: 404 });

  let body: { content?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  if (typeof body.content !== "string") {
    return NextResponse.json({ error: "body.content must be a string" }, { status: 400 });
  }

  const yamlContent: string = body.content;
  if (Buffer.byteLength(yamlContent, "utf-8") > MAX_YAML_BYTES) {
    return NextResponse.json({ error: "eval.yaml too large (max 256 KiB)" }, { status: 413 });
  }

  const evalYamlPath = path.join(wsPath, "eval.yaml");
  // Ensure the resolved path is still inside the workspace
  const resolvedTarget = path.resolve(evalYamlPath);
  if (!resolvedTarget.startsWith(wsPath + path.sep) && resolvedTarget !== path.join(wsPath, "eval.yaml")) {
    return NextResponse.json({ error: "invalid path" }, { status: 400 });
  }

  fs.writeFileSync(evalYamlPath, yamlContent, "utf-8");
  return NextResponse.json({ saved: true });
}
