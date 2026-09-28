import { redirect } from "next/navigation";
import { listRuns } from "@/lib/api";
import { RunList } from "@/components/RunList";
import { isServerMode } from "@/lib/server-mode";

export default async function HomePage() {
  if (isServerMode()) redirect("/workspaces");

  const runs = await listRuns();

  return (
    <div>
      <h2 className="text-xl font-semibold mb-6">Runs</h2>
      <RunList runs={runs} />
    </div>
  );
}
