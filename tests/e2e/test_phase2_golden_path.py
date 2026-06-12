"""ISSUE-2: Phase 2 golden path E2E — trace + judge (mock) + decision.json + report.

Acceptance criteria:
- repetitions >= 3, two configurations, trace + judge (mock client) both enabled
- decision.json exists and contains decision_report_id + per-configuration pass@k
- TraceRef is persisted
- judge EvaluationResult does NOT override a deterministic validation failure
- report output contains cost source annotation
- judge uses mock client — zero network dependency
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import micro_eval.engine.kernel as kernel_module
from micro_eval.config.planner import build_run_plan
from micro_eval.engine.kernel import ExecutionKernel
from micro_eval.evaluation.llm_judge import JudgeOutcome
from micro_eval.models.configuration import (
    AgentSpec,
    ConfigurationSpec,
    Guardrails,
    JudgeConfig,
    ProjectConfigV2,
)
from micro_eval.models.task import TaskSpec


class _AlwaysPassJudge:
    """Mock judge that always scores 1.0 — used to verify it cannot override
    a deterministic validation failure."""

    name = "fake-judge-golden-path"

    def judge(self, *, prompt, cell, result, config):  # noqa: ANN001
        return JudgeOutcome(
            score=1.0, pass_fail="pass", rationale="mock rationale", scores={"overall": 1.0}
        )


def _make_config(
    *,
    baseline_command: list[str],
    candidate_command: list[str],
    repetitions: int = 3,
    judge_enabled: bool = True,
) -> ProjectConfigV2:
    config = ProjectConfigV2(
        project_name="phase2-golden-path",
        configurations=[
            ConfigurationSpec(
                id="baseline",
                name="Baseline",
                repetitions=repetitions,
                agent=AgentSpec(name="baseline", command=baseline_command),
            ),
            ConfigurationSpec(
                id="candidate",
                name="Candidate",
                repetitions=repetitions,
                agent=AgentSpec(name="candidate", command=candidate_command),
            ),
        ],
        guardrails=Guardrails(max_concurrency=2),
    )
    if judge_enabled:
        config.judge = JudgeConfig(enabled=True, model="mock-model")
    config.config_hash = "config-hash-p2-golden"
    return config


def test_phase2_decision_json_has_report_id_and_pass_at_k(tmp_path: Path, monkeypatch) -> None:
    """decision.json exists, has decision_report_id, per-configuration pass@k."""
    monkeypatch.setattr(kernel_module, "resolve_judge_client", lambda _config: _AlwaysPassJudge())

    task = TaskSpec(
        id="golden-task",
        name="Golden task",
        input_payload="",
        expectations=[{"type": "contains", "value": "ok", "stream": "stdout"}],
        rubric="Score output correctness",
    )
    config = _make_config(
        baseline_command=[sys.executable, "-c", "print('ok')"],
        candidate_command=[sys.executable, "-c", "print('ok')"],
    )
    plan = build_run_plan(config, [task], project_root=tmp_path)
    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))

    decision_path = tmp_path / ".micro-eval" / "runs" / record.id / "decision.json"

    # decision.json must exist
    assert decision_path.exists(), "decision.json must be written after run"

    decision_data = json.loads(decision_path.read_text())
    # Must have decision_report_id
    assert decision_data.get("decision_report_id"), "decision_report_id must be non-empty"

    # per-configuration pass@k
    assert record.decision is not None
    for cfg_id in ("baseline", "candidate"):
        stats = record.decision.aggregation.per_configuration[cfg_id]
        assert stats.pass_at_k is not None, f"pass_at_k missing for {cfg_id}"
        assert len(stats.pass_at_k) > 0, f"pass_at_k is empty for {cfg_id}"


def test_phase2_trace_ref_is_persisted(tmp_path: Path, monkeypatch) -> None:
    """Each cell should have a TraceRef in run.traces and in cell.trace_refs."""
    monkeypatch.setattr(kernel_module, "resolve_judge_client", lambda _config: _AlwaysPassJudge())

    task = TaskSpec(id="trace-task", name="Trace task", input_payload="")
    config = _make_config(
        baseline_command=[sys.executable, "-c", "print('hello')"],
        candidate_command=[sys.executable, "-c", "print('world')"],
    )
    plan = build_run_plan(config, [task], project_root=tmp_path)
    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))

    # Traces must be persisted
    assert len(record.traces) > 0, "run must have at least one TraceRef"
    for result in record.results:
        assert len(result.trace_refs) > 0, f"cell {result.cell_id} has no trace_refs"


def test_phase2_judge_does_not_override_deterministic_failure(tmp_path: Path, monkeypatch) -> None:
    """Judge giving 1.0 must NOT flip a deterministic validation failure to pass/improved."""
    monkeypatch.setattr(kernel_module, "resolve_judge_client", lambda _config: _AlwaysPassJudge())

    task = TaskSpec(
        id="override-guard-task",
        name="Override guard task",
        input_payload="",
        expectations=[{"type": "contains", "value": "expected-text", "stream": "stdout"}],
        rubric="Score correctness",
    )
    # baseline passes, candidate fails validation (output does not contain expected-text)
    config = _make_config(
        baseline_command=[sys.executable, "-c", "print('expected-text')"],
        candidate_command=[sys.executable, "-c", "print('wrong-output')"],
    )
    plan = build_run_plan(config, [task], project_root=tmp_path)
    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))

    # All candidate cells must remain fail despite judge giving pass
    candidate_results = [r for r in record.results if r.configuration_id == "candidate"]
    for result in candidate_results:
        assert result.pass_fail == "fail", (
            f"candidate cell {result.cell_id} must stay fail even when judge gave pass"
        )

    # Verdict must not be "improved" (candidate is worse)
    assert record.decision is not None
    assert record.decision.verdict.value != "improved", (
        f"verdict must not be improved when candidate fails deterministic validation, got: {record.decision.verdict.value}"
    )

    # Judge evaluations should exist but not flip the result
    judge_evals = [e for e in record.evaluations if e.evaluator_type == "llm_judge"]
    assert len(judge_evals) > 0, "judge evaluations must be recorded even when overridden"


def test_phase2_report_output_contains_cost_source(tmp_path: Path, monkeypatch) -> None:
    """CLI report output must mention cost source."""
    monkeypatch.setattr(kernel_module, "resolve_judge_client", lambda _config: _AlwaysPassJudge())

    task = TaskSpec(
        id="cost-task",
        name="Cost task",
        input_payload="",
        expectations=[{"type": "contains", "value": "ok", "stream": "stdout"}],
    )
    config = _make_config(
        baseline_command=[sys.executable, "-c", "print('ok')"],
        candidate_command=[sys.executable, "-c", "print('ok')"],
    )
    plan = build_run_plan(config, [task], project_root=tmp_path)
    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))

    # Run CLI report in JSON format and check cost source is present
    result = subprocess.run(
        [sys.executable, "-m", "micro_eval.cli.main", "report", "--run", record.id, "--format", "json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"report failed: {result.stderr}"
    report_data = json.loads(result.stdout)
    # Cost source must be propagated through to the report JSON
    per_config = (
        report_data.get("decision", {})
        or report_data.get("aggregation", {})
    )
    # Flatten to text and check "source" field is present
    report_text = json.dumps(report_data)
    assert '"source"' in report_text, (
        f"report JSON must reference cost source field, got:\n{report_text[:500]}"
    )
