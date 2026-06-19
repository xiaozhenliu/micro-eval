import Link from "next/link";
import { notFound } from "next/navigation";
import fs from "node:fs";
import path from "node:path";
import { readWorkspaceMeta, resolveWorkspacePath } from "@/lib/workspace-api";
import { ConfigEditor } from "@/components/ConfigEditor";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function WorkspaceConfigPage({ params }: PageProps) {
  const { id } = await params;
  const meta = readWorkspaceMeta(id);
  if (!meta) notFound();

  const wsPath = resolveWorkspacePath(id);
  let configContent = "";
  if (wsPath) {
    const evalYamlPath = path.join(wsPath, "eval.yaml");
    if (fs.existsSync(evalYamlPath)) {
      configContent = fs.readFileSync(evalYamlPath, "utf-8");
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <Link href={`/workspace/${id}`} className="text-sm text-blue-400 hover:underline">
          ← {meta.name}
        </Link>
        <h2 className="mt-2 text-xl font-semibold">Config: {meta.name}</h2>
        <p className="mt-1 text-sm text-neutral-400">Edit eval.yaml for this workspace.</p>
      </div>

      {wsPath ? (
        <ConfigEditor workspaceId={id} initialContent={configContent} />
      ) : (
        <p className="text-sm text-red-400">Workspace directory not found.</p>
      )}
    </div>
  );
}
