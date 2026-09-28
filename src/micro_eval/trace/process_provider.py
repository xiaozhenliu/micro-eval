"""Built-in process-level trace provider."""

from __future__ import annotations

from micro_eval.engine.adapter import Redactor
from micro_eval.models.artifact import TraceRef
from micro_eval.models.decision import CostMetric
from micro_eval.models.run import AdapterResult, RunCell


class ProcessTraceProvider:
    """Record local process facts as the always-available trace fallback."""

    name = "process"

    def collect(self, cell: RunCell, result: AdapterResult, redactor: Redactor) -> TraceRef:
        """Return a redacted process trace summary."""
        failure_mode = redactor.redact(result.failure_mode or "") or None
        return TraceRef(
            trace_id=result.trace_id or cell.cell_id,
            provider=self.name,
            external_url=None,
            cost=CostMetric(amount=None, source="unavailable"),
            summary={
                "cell_id": cell.cell_id,
                "status": result.status.value,
                "exit_code": result.exit_code,
                "latency_s": result.latency_s,
                "timed_out": result.timed_out,
                "failure_mode": failure_mode,
            },
        )
