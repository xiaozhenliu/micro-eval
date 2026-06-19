import Link from "next/link";

export interface TemplateMeta {
  template_id: string;
  name: string;
  description?: string;
  version: string;
  author: string;
  tags: string[];
}

export function TemplateCard({ template }: { template: TemplateMeta }) {
  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-lg p-4 hover:border-neutral-700 transition-colors">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <Link
            href={`/templates/${template.template_id}`}
            className="text-blue-400 hover:underline font-medium truncate block"
          >
            {template.name}
          </Link>
          {template.description && (
            <p className="mt-1 text-sm text-neutral-400 line-clamp-2">
              {template.description}
            </p>
          )}
        </div>
        <span className="text-xs text-neutral-500 shrink-0 font-mono">
          v{template.version}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-neutral-400">
        <span>By {template.author}</span>
        {template.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {template.tags.map((tag) => (
              <span
                key={tag}
                className="px-1.5 py-0.5 rounded bg-neutral-800 border border-neutral-700 text-neutral-300"
              >
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
