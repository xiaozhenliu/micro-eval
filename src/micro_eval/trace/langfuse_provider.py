"""Optional Langfuse trace provider adapter."""

from __future__ import annotations

import importlib
import os
from typing import Any

from micro_eval.engine.adapter import Redactor
from micro_eval.models.artifact import TraceRef
from micro_eval.models.decision import CostMetric
from micro_eval.models.run import AdapterResult, RunCell


class LangfuseProvider:
    """Collect trace metadata from Langfuse when SDK and credentials are available."""

    name = "langfuse"

    def __init__(self) -> None:
        self.host = os.environ.get("LANGFUSE_HOST")
        self.public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
        self.secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
        if not self.public_key or not self.secret_key:
            raise RuntimeError("Langfuse credentials are not configured")
        module = importlib.import_module("langfuse")
        client_cls = getattr(module, "Langfuse")
        kwargs = {"public_key": self.public_key, "secret_key": self.secret_key}
        if self.host:
            kwargs["host"] = self.host
        self.client = client_cls(**kwargs)

    @classmethod
    def from_env(cls) -> "LangfuseProvider | None":
        """Instantiate only when credentials and SDK are available."""
        if not os.environ.get("LANGFUSE_PUBLIC_KEY") or not os.environ.get("LANGFUSE_SECRET_KEY"):
            return None
        try:
            return cls()
        except Exception:
            return None

    def collect(self, cell: RunCell, result: AdapterResult, redactor: Redactor) -> TraceRef | None:
        """Fetch a Langfuse trace by micro-eval trace id and normalize selected metadata."""
        trace_id = result.trace_id or cell.cell_id
        trace = self._find_trace(trace_id)
        if trace is None:
            return None
        cost_amount = _read_first_number(trace, ["total_cost", "cost", "calculated_total_cost"])
        token_count = _read_first_number(trace, ["total_tokens", "usage.total", "usage.total_tokens"])
        external_url = self._trace_url(trace_id)
        summary = {
            "trace_id": trace_id,
            "provider": self.name,
            "total_tokens": token_count,
            "status": redactor.redact(str(_read_attr(trace, "status") or "")) or None,
        }
        return TraceRef(
            trace_id=trace_id,
            provider=self.name,
            external_url=external_url,
            cost=CostMetric(
                amount=cost_amount,
                source="langfuse_cost" if cost_amount is not None else "langfuse_tokens" if token_count is not None else "unavailable",
            ),
            summary=summary,
        )

    def _find_trace(self, trace_id: str) -> Any | None:
        if hasattr(self.client, "get_trace"):
            try:
                return self.client.get_trace(trace_id)
            except TypeError:
                pass
        if hasattr(self.client, "fetch_trace"):
            return self.client.fetch_trace(trace_id)
        if hasattr(self.client, "api") and hasattr(self.client.api, "trace"):
            return self.client.api.trace.get(trace_id)
        return None

    def _trace_url(self, trace_id: str) -> str | None:
        if not self.host:
            return None
        return f"{self.host.rstrip('/')}/trace/{trace_id}"


def _read_attr(obj: Any, name: str) -> Any:
    current = obj
    for part in name.split("."):
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
    return current


def _read_first_number(obj: Any, names: list[str]) -> float | None:
    for name in names:
        value = _read_attr(obj, name)
        if isinstance(value, int | float):
            return float(value)
    return None
