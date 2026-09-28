import type { Run } from "@/lib/schema";

export function CaveatBanner({ run }: { run: Run }) {
  const caveats = [
    ...(run.migration_warnings ?? []),
    ...(run.same_start_snapshot?.caveats ?? []),
    ...(run.decision?.caveats ?? []),
  ];
  const unique = Array.from(new Set(caveats));
  if (unique.length === 0) return null;
  return (
    <section className="border border-amber-500/30 bg-amber-500/10 rounded-lg p-4 mb-6">
      <h3 className="font-semibold text-amber-200 mb-2">Caveats</h3>
      <ul className="list-disc pl-5 space-y-1 text-sm text-amber-100/90">
        {unique.map((caveat) => (
          <li key={caveat}>{caveat}</li>
        ))}
      </ul>
    </section>
  );
}
