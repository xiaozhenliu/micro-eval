import type { TraceRef } from "@/lib/schema";

export function TraceViewer({ traces }: { traces: TraceRef[] }) {
  return (
    <section>
      <p className="text-neutral-400 mb-2">Trace</p>
      {traces.length === 0 ? (
        <p className="text-sm text-neutral-500">No trace collected.</p>
      ) : (
        <ul className="space-y-2 text-sm">
          {traces.map((trace) => (
            <li key={`${trace.provider}:${trace.trace_id}`} className="rounded border border-neutral-800 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-neutral-300">{trace.provider}</span>
                <span className="text-neutral-500">{trace.trace_id}</span>
                {trace.external_url && (
                  <a className="text-blue-400 hover:underline" href={trace.external_url} target="_blank" rel="noreferrer">
                    open trace
                  </a>
                )}
              </div>
              <div className="mt-1 text-xs text-neutral-500">
                cost: {trace.cost?.amount == null ? `unavailable (${trace.cost?.source ?? "unavailable"})` : `$${trace.cost.amount.toFixed(4)}`}
              </div>
              {trace.summary && (
                <dl className="mt-2 grid gap-1 text-xs text-neutral-400 md:grid-cols-2">
                  {Object.entries(trace.summary).map(([key, value]) => (
                    <div key={key}>
                      <dt className="inline text-neutral-500">{key}: </dt>
                      <dd className="inline break-all">{String(value)}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
