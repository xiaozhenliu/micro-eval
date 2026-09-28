import path from "node:path";
import fs from "node:fs";
import { NextResponse } from "next/server";
import { isServerMode, getServerDataRoot } from "@/lib/server-mode";
import { safeTemplateId } from "@/lib/server-validation";

interface RouteContext {
  params: Promise<{ id: string }>;
}

export async function GET(_request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const { id } = await context.params;
  const safe = safeTemplateId(id);
  if (!safe) return NextResponse.json({ error: "invalid template id" }, { status: 400 });

  const templatesDir = path.join(getServerDataRoot(), "templates");
  const tplDir = path.resolve(templatesDir, safe);
  // Path traversal guard
  if (!tplDir.startsWith(path.resolve(templatesDir) + path.sep)) {
    return NextResponse.json({ error: "invalid template id" }, { status: 400 });
  }

  const metaPath = path.join(tplDir, "template.json");
  if (!fs.existsSync(metaPath)) {
    return NextResponse.json({ error: "template not found" }, { status: 404 });
  }

  try {
    return NextResponse.json(JSON.parse(fs.readFileSync(metaPath, "utf-8")));
  } catch (err) {
    return NextResponse.json(
      { error: "failed to parse template", detail: String(err) },
      { status: 500 },
    );
  }
}
