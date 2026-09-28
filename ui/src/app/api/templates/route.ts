import path from "node:path";
import fs from "node:fs";
import { NextResponse } from "next/server";
import { isServerMode, getServerDataRoot } from "@/lib/server-mode";

interface TemplateMeta {
  schema_version: string;
  template_id: string;
  name: string;
  description: string;
  version: string;
  created_at: string;
  updated_at: string;
  author: string;
  tags: string[];
  includes: Record<string, unknown>;
}

export async function GET() {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const templatesDir = path.join(getServerDataRoot(), "templates");
  if (!fs.existsSync(templatesDir)) return NextResponse.json([]);

  const entries = fs.readdirSync(templatesDir, { withFileTypes: true });
  const templates: TemplateMeta[] = [];

  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const metaPath = path.join(templatesDir, entry.name, "template.json");
    if (!fs.existsSync(metaPath)) continue;
    try {
      templates.push(JSON.parse(fs.readFileSync(metaPath, "utf-8")) as TemplateMeta);
    } catch {
      continue;
    }
  }

  templates.sort((a, b) => a.name.localeCompare(b.name));
  return NextResponse.json(templates);
}
