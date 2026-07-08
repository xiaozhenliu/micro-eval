import Link from "next/link";
import fs from "node:fs";
import path from "node:path";
import { notFound } from "next/navigation";
import { isServerMode, getServerDataRoot } from "@/lib/server-mode";
import { TemplateCard } from "@/components/TemplateCard";
import type { TemplateMeta } from "@/components/TemplateCard";

export const dynamic = "force-dynamic";

function listTemplates(): TemplateMeta[] {
  const templatesDir = path.join(getServerDataRoot(), "templates");
  if (!fs.existsSync(templatesDir)) return [];

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

  return templates.sort((a, b) => a.name.localeCompare(b.name));
}

export default function TemplatesPage() {
  if (!isServerMode()) notFound();

  const templates = listTemplates();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Link href="/" className="text-sm text-blue-400 hover:underline">← Home</Link>
          </div>
          <h2 className="text-xl font-semibold">Templates</h2>
          <p className="mt-1 text-sm text-neutral-400">
            {templates.length} template{templates.length !== 1 ? "s" : ""} available
          </p>
        </div>
      </div>

      {templates.length === 0 ? (
        <div className="rounded-lg border border-neutral-800 py-16 text-center text-neutral-400">
          <p className="text-lg">No templates found.</p>
          <p className="mt-2 text-sm text-neutral-500">
            Add templates to <code className="bg-neutral-800 px-1.5 py-0.5 rounded text-xs">~/.micro-eval-server/templates/</code>
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {templates.map((tpl) => (
            <TemplateCard key={tpl.template_id} template={tpl} />
          ))}
        </div>
      )}
    </div>
  );
}
