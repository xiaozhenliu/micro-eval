import Link from "next/link";
import { notFound } from "next/navigation";
import { isServerMode } from "@/lib/server-mode";
import { readWorkspaceMeta } from "@/lib/workspace-api";
import { safeJobId } from "@/lib/server-validation";
import { JobStatus } from "@/components/JobStatus";

interface PageProps {
  params: Promise<{ id: string; jobId: string }>;
}

/**
 * Landing page after "Enqueue Run" (GRO-556). The job id is validated with
 * the same `safeJobId` rule the API uses; everything else is fetched by the
 * client component so the page reflects live queue state.
 */
export default async function WorkspaceJobPage({ params }: PageProps) {
  if (!isServerMode()) notFound();

  const { id, jobId } = await params;
  const meta = readWorkspaceMeta(id);
  if (!meta) notFound();
  if (!safeJobId(jobId)) notFound();

  return (
    <div className="space-y-6">
      <div>
        <Link href={`/workspace/${id}`} className="text-sm text-blue-400 hover:underline">
          ← {meta.name}
        </Link>
        <h2 className="mt-2 text-xl font-semibold">Run job</h2>
        <p className="mt-1 text-sm text-neutral-400">
          Waiting for the queue worker. You will be taken to the run page when it finishes.
        </p>
      </div>

      <JobStatus workspaceId={id} jobId={jobId} />
    </div>
  );
}
