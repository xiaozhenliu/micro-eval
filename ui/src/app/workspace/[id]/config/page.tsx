import Link from "next/link";
import { notFound } from "next/navigation";
import { readWorkspaceMeta, resolveWorkspacePath } from "@/lib/workspace-api";
import { readProjectDraft, readRawConfig, ProjectApiError } from "@/lib/project-api";
import type { ProjectDraft } from "@/lib/project-schema";
import { ConfigEditor } from "@/components/ConfigEditor";
import { ConfigurationList } from "@/components/ConfigurationList";
import { TaskList } from "@/components/TaskList";

interface PageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ tab?: string }>;
}

type Tab = "configurations" | "tasks" | "advanced";

const TABS: { id: Tab; label: string }[] = [
  { id: "configurations", label: "Configurations" },
  { id: "tasks", label: "Tasks" },
  { id: "advanced", label: "Advanced" },
];

function parseTab(raw: string | undefined): Tab {
  return raw === "tasks" || raw === "advanced" ? raw : "configurations";
}

export default async function WorkspaceConfigPage({ params, searchParams }: PageProps) {
  const { id } = await params;
  const { tab: rawTab } = await searchParams;
  const tab = parseTab(rawTab);

  const meta = readWorkspaceMeta(id);
  if (!meta) notFound();

  const wsPath = resolveWorkspacePath(id);
  const readOnly = meta.status !== "active";

  let draft: ProjectDraft | null = null;
  let draftError: string | null = null;
  if (wsPath) {
    try {
      draft = readProjectDraft(wsPath);
    } catch (err) {
      draftError = err instanceof ProjectApiError ? err.message : "failed to read project";
    }
  }

  let configContent = "";
  let configRedacted = false;
  let configError: string | null = null;
  if (wsPath) {
    try {
      const raw = readRawConfig(wsPath);
      configContent = raw.content;
      configRedacted = raw.redacted;
    } catch (err) {
      configError = err instanceof ProjectApiError ? err.message : "failed to read config";
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <Link href={`/workspace/${id}`} className="text-sm text-blue-400 hover:underline">
          ← {meta.name}
        </Link>
        <h2 className="mt-2 text-xl font-semibold">Config: {meta.name}</h2>
        <p className="mt-1 text-sm text-neutral-400">
          Set up configurations and tasks for this workspace, or edit eval.yaml directly.
        </p>
      </div>

      <div className="flex gap-1 border-b border-neutral-800">
        {TABS.map((t) => (
          <Link
            key={t.id}
            href={`/workspace/${id}/config?tab=${t.id}`}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.id
                ? "border-blue-500 text-neutral-100"
                : "border-transparent text-neutral-400 hover:text-neutral-200"
            }`}
          >
            {t.label}
          </Link>
        ))}
      </div>

      {readOnly && (
        <p className="rounded border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-300">
          This workspace is {meta.status}: configurations and tasks are read-only.
        </p>
      )}

      {draftError && (
        <p className="rounded border border-red-900/60 bg-red-950/30 px-3 py-2 text-sm text-red-300">{draftError}</p>
      )}

      {draft && draft.warnings.length > 0 && (
        <div className="rounded border border-amber-900/60 bg-amber-950/30 px-3 py-2 text-sm text-amber-300">
          <p className="font-medium">eval.yaml warnings</p>
          <ul className="mt-1 list-disc pl-5">
            {draft.warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      {!wsPath ? (
        <p className="text-sm text-red-400">Workspace directory not found.</p>
      ) : (
        <>
          {tab === "configurations" &&
            (draft ? (
              <ConfigurationList workspaceId={id} initialDraft={draft} readOnly={readOnly} />
            ) : (
              <p className="text-sm text-neutral-400">Configurations are unavailable until eval.yaml can be read.</p>
            ))}

          {tab === "tasks" &&
            (draft ? (
              <TaskList workspaceId={id} initialDraft={draft} readOnly={readOnly} />
            ) : (
              <p className="text-sm text-neutral-400">Tasks are unavailable until eval.yaml can be read.</p>
            ))}

          {tab === "advanced" && (
            <div className="space-y-3">
              <p className="text-sm text-neutral-400">
                Saving from the Configurations or Tasks forms rewrites this file; comments are not preserved.
              </p>
              {configError && (
                <p className="rounded border border-red-900/60 bg-red-950/30 px-3 py-2 text-sm text-red-300">
                  {configError}
                </p>
              )}
              <ConfigEditor
                workspaceId={id}
                initialContent={configContent}
                redacted={configRedacted}
                readFailed={configError !== null}
              readOnly={readOnly}
            />
            </div>
          )}
        </>
      )}
    </div>
  );
}
