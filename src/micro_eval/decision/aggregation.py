"""Pure aggregation helpers for repetitions and decision statistics."""

from __future__ import annotations

from math import comb
from statistics import mean, median
from typing import Literal

from micro_eval.models.artifact import TraceRef
from micro_eval.models.decision import AggregationResult, ConfigurationStats, CostMetric
from micro_eval.models.run import CellResult, CellStatus

DenominatorPolicy = Literal["include_failed", "exclude_failed"]


def build_aggregation(
    results: list[CellResult],
    *,
    traces: list[TraceRef] | None = None,
    denominator_policy: DenominatorPolicy = "include_failed",
) -> AggregationResult:
    """Aggregate cell results into pass@k/pass^k and honest stats."""
    by_config: dict[str, list[CellResult]] = {}
    for result in results:
        by_config.setdefault(result.configuration_id, []).append(result)

    trace_by_id = {trace.trace_id: trace for trace in traces or []}
    per_configuration = {
        config_id: aggregate_configuration(
            results,
            traces=[trace_by_id[result.cell_id] for result in results if result.cell_id in trace_by_id],
            denominator_policy=denominator_policy,
        )
        for config_id, results in by_config.items()
    }
    return AggregationResult(per_configuration=per_configuration)


def aggregate_configuration(
    results: list[CellResult],
    *,
    traces: list[TraceRef] | None = None,
    denominator_policy: DenominatorPolicy = "include_failed",
) -> ConfigurationStats:
    """Aggregate all cells for one configuration."""
    n_cells = len(results)
    successful_results = [result for result in results if result.status in {CellStatus.passed, CellStatus.failed}]
    n_successful = len(successful_results)
    binary_results = [result for result in results if _has_binary_outcome(result)]
    caveats: list[str] = []
    if n_successful < 3:
        caveats.append("low_sample")

    denominator_results = results if denominator_policy == "include_failed" else successful_results
    denominator = len(denominator_results)
    passed = sum(1 for result in denominator_results if _is_pass(result))
    has_binary_signal = bool(binary_results)
    pass_rate = passed / denominator if has_binary_signal and denominator else None
    pass_at_k = _pass_at_k(denominator, passed) if pass_rate is not None else None
    pass_hat_k = _pass_hat_k(denominator, pass_rate) if pass_rate is not None else None

    latencies = [result.latency_s * 1000.0 for result in results]
    return ConfigurationStats(
        n_cells=n_cells,
        n_successful=n_successful,
        pass_rate=pass_rate,
        pass_at_k=pass_at_k,
        pass_hat_k=pass_hat_k,
        mean_latency_ms=mean(latencies) if latencies else None,
        median_latency_ms=median(latencies) if latencies else None,
        total_cost=_aggregate_cost(traces or []),
        denominator_policy=denominator_policy,
        caveats=caveats,
    )


def _has_binary_outcome(result: CellResult) -> bool:
    return result.pass_fail in {"pass", "fail"} or result.status in {CellStatus.passed, CellStatus.failed}


def _is_pass(result: CellResult) -> bool:
    if result.pass_fail is not None:
        return result.pass_fail == "pass"
    return result.status == CellStatus.passed


def _pass_at_k(n: int, c: int) -> dict[int, float]:
    """Return unbiased pass@k estimates for k=1..n."""
    if n <= 0:
        return {}
    values: dict[int, float] = {}
    for k in range(1, n + 1):
        if n - c < k:
            values[k] = 1.0
        else:
            values[k] = 1.0 - (comb(n - c, k) / comb(n, k))
    return values


def _pass_hat_k(n: int, pass_rate: float) -> dict[int, float]:
    """Return pass^k estimates for k=1..n."""
    if n <= 0:
        return {}
    return {k: pass_rate**k for k in range(1, n + 1)}


def _aggregate_cost(traces: list[TraceRef]) -> CostMetric | None:
    """Aggregate trace costs while preserving source caveats."""
    if not traces:
        return CostMetric(amount=None, source="unavailable")
    amounts = [trace.cost.amount for trace in traces if trace.cost is not None and trace.cost.amount is not None]
    if not amounts:
        source = next((trace.cost.source for trace in traces if trace.cost is not None), "unavailable")
        return CostMetric(amount=None, source=source or "unavailable")
    sources = sorted({trace.cost.source for trace in traces if trace.cost is not None and trace.cost.amount is not None})
    return CostMetric(amount=sum(amounts), source=" + ".join(sources) if sources else "trace")
