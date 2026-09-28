"""Trace provider fallback and cost aggregation coverage."""

from __future__ import annotations

from micro_eval.decision.aggregation import aggregate_configuration
from micro_eval.engine.adapter import Redactor
from micro_eval.models.artifact import TraceRef
from micro_eval.models.configuration import AgentSpec, ConfigurationSpec
from micro_eval.models.decision import CostMetric
from micro_eval.models.run import AdapterResult, CellStatus, RunCell, CellResult
from micro_eval.models.task import TaskSpec
from micro_eval.trace.process_provider import ProcessTraceProvider
from micro_eval.trace.provider import collect_trace_with_fallback


def test_process_provider_returns_unavailable_cost_and_redacted_summary() -> None:
    cell = _run_cell("cell-secret")
    result = AdapterResult(
        status=CellStatus.error,
        exit_code=1,
        latency_s=0.5,
        failure_mode="token secret-value leaked",
        trace_id=cell.cell_id,
    )

    trace = ProcessTraceProvider().collect(cell, result, Redactor({"MICRO_EVAL_SECRET_TOKEN": "secret-value"}))

    assert trace.provider == "process"
    assert trace.cost is not None
    assert trace.cost.amount is None
    assert trace.cost.source == "unavailable"
    assert trace.summary is not None
    assert "secret-value" not in str(trace.summary)
    assert "[REDACTED:MICRO_EVAL_SECRET_TOKEN]" in str(trace.summary)


def test_trace_collection_falls_back_when_primary_provider_fails() -> None:
    class BrokenProvider:
        name = "broken"

        def collect(self, cell, result, redactor):  # noqa: ANN001
            raise RuntimeError("network down")

    cell = _run_cell("cell-fallback")
    result = AdapterResult(status=CellStatus.passed, trace_id=cell.cell_id)

    trace = collect_trace_with_fallback(
        [BrokenProvider(), ProcessTraceProvider()],
        cell=cell,
        result=result,
        redactor=Redactor({}),
    )

    assert trace is not None
    assert trace.provider == "process"
    assert trace.summary is not None
    assert "fallback_warnings" in trace.summary


def test_cost_ladder_uses_trace_cost_before_unavailable_fallback() -> None:
    result = _cell_result("cell-cost")
    stats = aggregate_configuration(
        [result],
        traces=[
            TraceRef(
                trace_id="cell-cost",
                provider="langfuse",
                cost=CostMetric(amount=0.25, source="langfuse_cost"),
            )
        ],
    )

    assert stats.total_cost is not None
    assert stats.total_cost.amount == 0.25
    assert stats.total_cost.source == "langfuse_cost"


def test_cost_ladder_marks_cost_unavailable_without_trace_cost() -> None:
    stats = aggregate_configuration([_cell_result("cell-no-cost")])

    assert stats.total_cost is not None
    assert stats.total_cost.amount is None
    assert stats.total_cost.source == "unavailable"


def _run_cell(cell_id: str) -> RunCell:
    config = ConfigurationSpec(id="cfg", name="cfg", agent=AgentSpec(name="agent", command=["python", "-c", "print('ok')"]))
    return RunCell(cell_id=cell_id, task=TaskSpec(id="task", name="task", input_payload=""), configuration=config)


def _cell_result(cell_id: str) -> CellResult:
    return CellResult(
        cell_id=cell_id,
        run_id="run-trace",
        task_id="task",
        configuration_id="cfg",
        configuration_name="cfg",
        repetition=1,
        status=CellStatus.passed,
        pass_fail="pass",
    )
