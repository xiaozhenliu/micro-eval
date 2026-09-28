import Link from "next/link";
import fs from "node:fs";
import path from "node:path";
import { notFound } from "next/navigation";
import { isServerMode, getServerDataRoot } from "@/lib/server-mode";
import { safeTemplateId } from "@/lib/server-validation";
import type { TemplateMeta } from "@/components/TemplateCard";

export const dynamic = "force-dynamic";

interface FullTemplateMeta extends TemplateMeta {
  schema_version?: string;
  created_at?: string;
  updated_at?: string;
  includes?: Record<string, unknown>;
}

interface PageProps {
  params: Promise<{ id: string }>;
}

function loadTemplate(id: string): FullTemplateMeta | null {
  const safe = safeTemplateId(id);
  if (!safe) return null;

  const templatesDir = path.join(getServerDataRoot(), "templates");
  const tplDir = path.resolve(templatesDir, safe);
  if (!tplDir.startsWith(path.resolve(templatesDir) + path.sep)) return null;

  const metaPath = path.join(tplDir, "template.json");
  if (!fs.existsSync(metaPath)) return null;

  try {
    return JSON.parse(fs.readFileSync(metaPath, "utf-8")) as FullTemplateMeta;
  } catch {
    return null;
  }
}

export default async function TemplateDetailPage({ params }: PageProps) {
  if (!isServerMode()) notFound();

  const { id } = await params;
  const template = loadTemplate(id);
  if (!template) notFound();

  const includeEntries = template.includes ? Object.entries(template.includes) : [];

  return (
    <div className="space-y-6">
      <div>
        <Link href="/templates" className="text-sm text-blue-400 hover:underline">← Templates</Link>
        <h2 className="mt-2 text-xl font-semibold">{template.name}</h2>
        {template.description && (
          <p className="mt-1 text-sm text-neutral-400">{template.description}</p>
        )}
      </div>

      <div className="rounded-lg border border-neutral-800 bg-neutral-900 p-4 space-y-3">
        <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <div>
            <span className="text-neutral-500">ID</span>
            <p className="mt-0.5 font-mono text-xs text-neutral-300">{template.template_id}</p>
          </div>
          <div>
            <span className="text-neutral-500">Version</span>
            <p className="mt-0.5 text-neutral-300">v{template.version}</p>
          </div>
          <div>
            <span className="text-neutral-500">Author</span>
            <p className="mt-0.5 text-neutral-300">{template.author}</p>
          </div>
          {template.created_at && (
            <div>
              <span className="text-neutral-500">Created</span>
              <p className="mt-0.5 text-neutral-300">{new Date(template.created_at).toLocaleDateString()}</p>
            </div>
          )}
        </div>

        {template.tags && template.tags.length > 0 && (
          <div>
            <span className="text-sm text-neutral-500">Tags</span>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {template.tags.map((tag) => (
                <span
                  key={tag}
                  className="px-2 py-0.5 rounded-full bg-neutral-800 border border-neutral-700 text-xs text-neutral-300"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {includeEntries.length > 0 && (
        <div>
          <h3 className="text-base font-medium mb-3">Includes</h3>
          <div className="space-y-2">
            {includeEntries.map(([key, value]) => (
              <div key={key} className="rounded border border-neutral-800 bg-neutral-900 p-3">
                <p className="text-sm font-mono text-neutral-300">{key}</p>
                {value != null && (
                  <p className="mt-1 text-xs text-neutral-500 font-mono">
                    {typeof value === "object" ? JSON.stringify(value) : String(value)}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <Link
          href={`/workspaces/new?template=${template.template_id}`}
          className="inline-block rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
        >
          Use this template
        </Link>
      </div>
    </div>
  );
}
