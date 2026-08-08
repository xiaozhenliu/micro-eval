#!/usr/bin/env python3
"""Generate deterministic golden contract fixtures for cross-language schema testing.

All timestamps, IDs, and digests are fixed literals — no datetime.now(), no random,
no environment variable reads. This guarantees idempotent output.

Outputs written to tests/contract/golden/ (committed to the repository).
The canonical-run-p0.json fixture (also consumed by check-version-consistency.py)
is written to its original path ui/src/lib/fixtures/canonical-run-p0.json so that
the release preflight script continues to work without any path changes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from micro_eval.decision.summary import build_decision
from micro_eval.models.run import RunRecord

# Resolve repo root relative to this file.
REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = REPO_ROOT / "tests" / "contract" / "golden"
GOLDEN_DIR.mkdir(parents=True, exist_ok=True)


def _write(name: str, data: dict) -> None:  # type: ignore[type-arg]
    """Write a golden file with deterministic formatting."""
    path = GOLDEN_DIR / name
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {path.relative_to(REPO_ROOT)}")


# ---------------------------------------------------------------------------
# RunRecord — Phase 2 full variant (all optional fields populated)
# ---------------------------------------------------------------------------

RUN_PHASE2_FULL: dict = {  # type: ignore[type-arg]
    "schema_version": "1.0",
    "id": "run-phase2-fixture",
    "project_name": "phase2-fixture",
    "status": "completed",
    "created_at": "2026-06-12T00:00:00+00:00",
    "completed_at": "2026-06-12T00:01:00+00:00",
    "failure_reason": None,
    "output_dir": ".micro-eval/runs",
    "config_hash": "config-hash-p2",
    "tasks": ["task-p2"],
    "configurations": ["baseline", "candidate"],
    "cells": ["cell-b1", "cell-b2", "cell-b3", "cell-c1", "cell-c2", "cell-c3"],
    "execution_order": ["cell-b1", "cell-b2", "cell-b3", "cell-c1", "cell-c2", "cell-c3"],
    "execution_seed": None,
    "results": [
        {
            "schema_version": "1.0",
            "cell_id": "cell-b1",
            "run_id": "run-phase2-fixture",
            "task_id": "task-p2",
            "configuration_id": "baseline",
            "configuration_name": "Baseline",
            "repetition": 1,
            "status": "pass",
            "score": 1.0,
            "pass_fail": "pass",
            "output_summary": "ok",
            "stdout_summary": "ok",
            "stderr_summary": "",
            "exit_code": 0,
            "latency_s": 0.1,
            "failure_mode": None,
            "artifact_refs": ["cell-b1::stdout::abc111"],
            "evidence_refs": ["cell-b1::evidence::process"],
            "evaluation_refs": ["cell-b1::validator::abc111", "cell-b1::llm-judge::abc111"],
            "trace_refs": ["process:cell-b1"],
            "cell_snapshot": {
                "schema_version": "1.0",
                "workspace_path": "/tmp/ws/b1",
                "git_commit": None,
                "dirty": None,
                "setup_exit_code": None,
                "timestamp": "2026-06-12T00:00:00+00:00",
                "cleanup_status": "cleaned",
                "cleanup_error": None,
            },
            "snapshot_gate_result": {
                "schema_version": "1.0",
                "status": "pass",
                "mismatch_fields": [],
                "gate_version": "1.0",
                "caveats": [],
            },
        },
        {
            "schema_version": "1.0",
            "cell_id": "cell-c1",
            "run_id": "run-phase2-fixture",
            "task_id": "task-p2",
            "configuration_id": "candidate",
            "configuration_name": "Candidate",
            "repetition": 1,
            "status": "fail",
            "score": 0.0,
            "pass_fail": "fail",
            "output_summary": "missing expected",
            "stdout_summary": "actual",
            "stderr_summary": "",
            "exit_code": 0,
            "latency_s": 0.2,
            "failure_mode": None,
            "artifact_refs": ["cell-c1::stdout::abc121"],
            "evidence_refs": ["cell-c1::evidence::process"],
            "evaluation_refs": ["cell-c1::validator::abc121", "cell-c1::llm-judge::abc121"],
            "trace_refs": ["process:cell-c1"],
            "cell_snapshot": {
                "schema_version": "1.0",
                "workspace_path": "/tmp/ws/c1",
                "git_commit": None,
                "dirty": None,
                "setup_exit_code": None,
                "timestamp": "2026-06-12T00:00:00+00:00",
                "cleanup_status": "cleaned",
                "cleanup_error": None,
            },
            "snapshot_gate_result": {
                "schema_version": "1.0",
                "status": "pass",
                "mismatch_fields": [],
                "gate_version": "1.0",
                "caveats": [],
            },
        },
    ],
    "migration_warnings": [],
    "same_start_snapshot": {
        "schema_version": "1.0",
        "workspace_type": "blank",
        "git_commit": None,
        "dirty": None,
        "config_hash": "config-hash-p2",
        "configuration_digests": {"baseline": "digest-b", "candidate": "digest-c"},
        "task_revisions": {"task-p2": "revision-p2"},
        "python_version": "3.11.0",
        "setup_commands_digest": None,
        "guardrails_digest": "guardrails-p2",
        "sandbox_resource_limits": None,
        "workspace_map": None,
        "timestamp": "2026-06-12T00:00:00+00:00",
        "caveats": [],
    },
    "replay_canonical": {
        "schema_version": "1.0",
        "tool_version": "0.2.0",
        "config_hash": "config-hash-p2",
        "task_ids": ["task-p2"],
        "task_revisions": {"task-p2": "revision-p2"},
        "configuration_ids": ["baseline", "candidate"],
        "configuration_digests": {"baseline": "digest-b", "candidate": "digest-c"},
        "workspace_type": "blank",
        "git_commit": None,
        "workspace_map": None,
        "workspace_fingerprint": "workspace-fp-p2",
        "setup_commands_digest": None,
        "guardrails_digest": "guardrails-p2",
        "max_concurrency": 2,
        "digest": "replay-digest-p2",
    },
    "artifacts": [
        {
            "schema_version": "1.0",
            "artifact_id": "cell-b1::stdout::abc111",
            "kind": "stdout",
            "path": "cells/cell-b1/stdout.txt",
            "sha256": "abc111",
            "size_bytes": 3,
            "media_type": "text/plain",
            "redacted": True,
            "warning": None,
        },
        {
            "schema_version": "1.0",
            "artifact_id": "cell-c1::stdout::abc121",
            "kind": "stdout",
            "path": "cells/cell-c1/stdout.txt",
            "sha256": "abc121",
            "size_bytes": 6,
            "media_type": "text/plain",
            "redacted": True,
            "warning": None,
        },
    ],
    "evidence": [
        {
            "schema_version": "1.0",
            "evidence_id": "cell-b1::evidence::process",
            "kind": "process",
            "summary": "status=pass exit_code=0",
            "source_kind": "artifact_ref",
            "source_ref": "cell-b1::stdout::abc111",
            "cell_id": "cell-b1",
            "status": "passed",
            "severity": "info",
            "artifact_refs": ["cell-b1::stdout::abc111"],
            "metadata": {},
        },
        {
            "schema_version": "1.0",
            "evidence_id": "cell-b1::evidence::judge",
            "kind": "judge_rationale",
            "summary": "Judge: looks good",
            "source_kind": "evaluation_ref",
            "source_ref": "cell-b1::llm-judge::abc111",
            "cell_id": "cell-b1",
            "status": "passed",
            "severity": "info",
            "artifact_refs": [],
            "metadata": {},
        },
        {
            "schema_version": "1.0",
            "evidence_id": "cell-c1::evidence::process",
            "kind": "process",
            "summary": "status=fail exit_code=0",
            "source_kind": "artifact_ref",
            "source_ref": "cell-c1::stdout::abc121",
            "cell_id": "cell-c1",
            "status": "failed",
            "severity": "error",
            "artifact_refs": ["cell-c1::stdout::abc121"],
            "metadata": {},
        },
        {
            "schema_version": "1.0",
            "evidence_id": "cell-c1::evidence::judge",
            "kind": "judge_rationale",
            "summary": "Judge: does not meet criteria",
            "source_kind": "evaluation_ref",
            "source_ref": "cell-c1::llm-judge::abc121",
            "cell_id": "cell-c1",
            "status": "failed",
            "severity": "warning",
            "artifact_refs": [],
            "metadata": {},
        },
    ],
    "traces": [
        {
            "schema_version": "1.0",
            "trace_id": "cell-b1",
            "provider": "process",
            "external_url": None,
            "cost": {
                "schema_version": "1.0",
                "amount": None,
                "currency": "USD",
                "source": "unavailable",
            },
            "summary": {"latency_ms": 100},
        },
        {
            "schema_version": "1.0",
            "trace_id": "cell-c1",
            "provider": "process",
            "external_url": None,
            "cost": {
                "schema_version": "1.0",
                "amount": None,
                "currency": "USD",
                "source": "unavailable",
            },
            "summary": {"latency_ms": 200},
        },
    ],
    "evaluations": [
        {
            "schema_version": "1.0",
            "evaluation_id": "cell-b1::validator::abc111",
            "cell_id": "cell-b1",
            "evaluator_type": "validator",
            "evaluator": "micro-eval-deterministic-validator",
            "pass_fail": "pass",
            "score": 1.0,
            "scores": {},
            "evaluator_meta": None,
            "rubric_hash": None,
            "comment": "ok",
            "evidence_refs": ["cell-b1::evidence::process"],
            "created_at": "20260612T000000Z",
        },
        {
            "schema_version": "1.0",
            "evaluation_id": "cell-b1::llm-judge::abc111",
            "cell_id": "cell-b1",
            "evaluator_type": "llm_judge",
            "evaluator": "fake-judge",
            "pass_fail": "pass",
            "score": 1.0,
            "scores": {"overall": 1.0},
            "evaluator_meta": None,
            "rubric_hash": "rubric-hash",
            "comment": "looks good",
            "evidence_refs": ["cell-b1::evidence::judge"],
            "created_at": "20260612T000000Z",
        },
        {
            "schema_version": "1.0",
            "evaluation_id": "cell-c1::validator::abc121",
            "cell_id": "cell-c1",
            "evaluator_type": "validator",
            "evaluator": "micro-eval-deterministic-validator",
            "pass_fail": "fail",
            "score": 0.0,
            "scores": {},
            "evaluator_meta": None,
            "rubric_hash": None,
            "comment": "missing expected",
            "evidence_refs": ["cell-c1::evidence::process"],
            "created_at": "20260612T000000Z",
        },
        {
            "schema_version": "1.0",
            "evaluation_id": "cell-c1::llm-judge::abc121",
            "cell_id": "cell-c1",
            "evaluator_type": "llm_judge",
            "evaluator": "fake-judge",
            "pass_fail": "pass",
            "score": 0.9,
            "scores": {"overall": 0.9},
            "evaluator_meta": None,
            "rubric_hash": "rubric-hash",
            "comment": "mostly good",
            "evidence_refs": ["cell-c1::evidence::judge"],
            "created_at": "20260612T000000Z",
        },
    ],
    "decision": {
        "schema_version": "1.0",
        "decision_report_id": "run-phase2-fixture::decision::20260612T000000Z",
        "verdict": "regressed",
        "confidence": "medium",
        "evaluation_refs": ["cell-b1::validator::abc111", "cell-c1::validator::abc121"],
        "evidence_refs": ["cell-b1::evidence::process", "cell-c1::evidence::process"],
        "caveats": [],
        "aggregation": {
            "schema_version": "1.0",
            "per_configuration": {
                "baseline": {
                    "schema_version": "1.0",
                    "n_cells": 3,
                    "n_successful": 3,
                    "pass_rate": 1.0,
                    "pass_at_k": {"1": 1.0, "2": 1.0, "3": 1.0},
                    "pass_hat_k": {"1": 1.0, "2": 1.0, "3": 1.0},
                    "mean_latency_ms": 110.0,
                    "median_latency_ms": 110.0,
                    "total_cost": {
                        "schema_version": "1.0",
                        "amount": None,
                        "currency": "USD",
                        "source": "unavailable",
                    },
                    "denominator_policy": "exclude_failed",
                    "caveats": [],
                },
                "candidate": {
                    "schema_version": "1.0",
                    "n_cells": 3,
                    "n_successful": 3,
                    "pass_rate": 0.0,
                    "pass_at_k": {"1": 0.0, "2": 0.0, "3": 0.0},
                    "pass_hat_k": {"1": 0.0, "2": 0.0, "3": 0.0},
                    "mean_latency_ms": 210.0,
                    "median_latency_ms": 210.0,
                    "total_cost": {
                        "schema_version": "1.0",
                        "amount": None,
                        "currency": "USD",
                        "source": "unavailable",
                    },
                    "denominator_policy": "exclude_failed",
                    "caveats": [],
                },
            },
        },
        "timestamp": "20260612T000000Z",
        "recommended_action": "investigate candidate regression",
        "created_at": "20260612T000000Z",
    },
    "denominator_policy": "exclude_failed",
    "owner": "fixture-owner",
    "server_context": {
        "schema_version": "1.0",
        "workspace_id": "ws-20260612T000000Z-12345678",
        "owner": "fixture-owner",
        "template_id": "phase2-template",
        "template_version": "1.0.0",
        "job_id": "job-20260612T000000Z-12345678",
        "server_name": "fixture-server",
    },
}

# ---------------------------------------------------------------------------
# RunRecord — minimal variant (all optional fields null/empty)
# ---------------------------------------------------------------------------

RUN_MINIMAL: dict = {  # type: ignore[type-arg]
    "schema_version": "1.0",
    "id": "run-minimal-fixture",
    "project_name": "minimal-fixture",
    "status": "planned",
    "created_at": "2026-06-12T00:00:00+00:00",
    "completed_at": None,
    "failure_reason": None,
    "output_dir": ".micro-eval/runs",
    "config_hash": "",
    "tasks": [],
    "configurations": [],
    "cells": [],
    "execution_order": [],
    "execution_seed": None,
    "results": [],
    "migration_warnings": [],
    "same_start_snapshot": None,
    "replay_canonical": None,
    "artifacts": [],
    "evidence": [],
    "traces": [],
    "evaluations": [],
    "decision": None,
    "denominator_policy": "include_failed",
}

# ---------------------------------------------------------------------------
# DecisionReport — standalone
# ---------------------------------------------------------------------------

DECISION_REPORT: dict = {  # type: ignore[type-arg]
    "schema_version": "1.0",
    "decision_report_id": "run-phase2-fixture::decision::20260612T000000Z",
    "verdict": "regressed",
    "confidence": "medium",
    "evaluation_refs": ["cell-b1::validator::abc111", "cell-c1::validator::abc121"],
    "evidence_refs": ["cell-b1::evidence::process", "cell-c1::evidence::process"],
    "caveats": [],
    "aggregation": {
        "schema_version": "1.0",
        "per_configuration": {
            "baseline": {
                "schema_version": "1.0",
                "n_cells": 3,
                "n_successful": 3,
                "pass_rate": 1.0,
                "pass_at_k": {"1": 1.0, "2": 1.0, "3": 1.0},
                "pass_hat_k": {"1": 1.0, "2": 1.0, "3": 1.0},
                "mean_latency_ms": 110.0,
                "median_latency_ms": 110.0,
                "total_cost": {
                    "schema_version": "1.0",
                    "amount": None,
                    "currency": "USD",
                    "source": "unavailable",
                },
                "denominator_policy": "include_failed",
                "caveats": [],
            },
            "candidate": {
                "schema_version": "1.0",
                "n_cells": 3,
                "n_successful": 3,
                "pass_rate": 0.0,
                "pass_at_k": {"1": 0.0, "2": 0.0, "3": 0.0},
                "pass_hat_k": {"1": 0.0, "2": 0.0, "3": 0.0},
                "mean_latency_ms": 210.0,
                "median_latency_ms": 210.0,
                "total_cost": {
                    "schema_version": "1.0",
                    "amount": None,
                    "currency": "USD",
                    "source": "unavailable",
                },
                "denominator_policy": "include_failed",
                "caveats": [],
            },
        },
    },
    "timestamp": "20260612T000000Z",
    "recommended_action": "investigate candidate regression",
    "created_at": "20260612T000000Z",
}

# ---------------------------------------------------------------------------
# TraceRef — standalone
# ---------------------------------------------------------------------------

TRACE_REF: dict = {  # type: ignore[type-arg]
    "schema_version": "1.0",
    "trace_id": "cell-b1",
    "provider": "langfuse",
    "external_url": "https://cloud.langfuse.com/trace/abc111",
    "cost": {
        "schema_version": "1.0",
        "amount": 0.001,
        "currency": "USD",
        "source": "langfuse",
    },
    "summary": {"latency_ms": 100, "tokens": 512},
}

# ---------------------------------------------------------------------------
# EvaluationResult — standalone
# ---------------------------------------------------------------------------

EVALUATION_RESULT: dict = {  # type: ignore[type-arg]
    "schema_version": "1.0",
    "evaluation_id": "cell-b1::llm-judge::abc111",
    "cell_id": "cell-b1",
    "evaluator_type": "llm_judge",
    "evaluator": "fake-judge",
    "pass_fail": "pass",
    "score": 0.95,
    "scores": {"overall": 0.95, "correctness": 1.0},
    "evaluator_meta": {"model": "gpt-4o-mini", "temperature": 0.0},
    "rubric_hash": "rubric-hash-abc",
    "comment": "Meets all criteria",
    "evidence_refs": ["cell-b1::evidence::judge"],
    "created_at": "20260612T000000Z",
}

# ---------------------------------------------------------------------------
# RunPlan — standalone
# ---------------------------------------------------------------------------

RUN_PLAN: dict = {  # type: ignore[type-arg]
    "schema_version": "1.0",
    "run_id": "run-plan-fixture",
    "project_name": "plan-fixture",
    "created_at": "2026-06-12T00:00:00+00:00",
    "output_dir": ".micro-eval/runs/run-plan-fixture",
    "guardrails": {
        "schema_version": "1.0",
        "max_output_bytes": 1048576,
        "max_stderr_bytes": 65536,
        "allow_network": False,
    },
    "trace": {
        "schema_version": "1.0",
        "enabled": False,
        "provider": "process",
    },
    "judge": {
        "schema_version": "1.0",
        "enabled": False,
        "model": "",
        "temperature": 0.0,
        "pass_threshold": 0.5,
        "provider": "deepeval",
        "required_secrets": [],
    },
    "cells": [
        {
            "schema_version": "1.0",
            "cell_id": "cell-plan-1",
            "task": {
                "schema_version": "1.0",
                "id": "task-plan-1",
                "name": "Hello World Task",
                "description": "Smoke-test task for RunPlan golden fixture",
                "input_payload": "Write hello world",
                "expected_output": "hello world",
                "workspace": {
                    "schema_version": "1.0",
                    "type": "blank",
                    "path": None,
                    "ref": None,
                    "files": [],
                    "setup": [],
                },
                "expectations": [],
                "rubric": None,
                "business_impact_tier": 3,
                "tags": [],
                "revision_id": "rev-plan-1",
            },
            "configuration": {
                "schema_version": "1.0",
                "id": "baseline",
                "name": "Baseline",
                "agent": {
                    "schema_version": "1.0",
                    "name": "test-agent",
                    "command": ["echo", "hello world"],
                    "input_mode": "stdin",
                    "output_mode": "stdout",
                    "timeout_s": 30.0,
                    "env": {},
                    "required_secrets": [],
                },
                "repetitions": 1,
                "role": None,
                "skills_profile": {},
                "parameters": {},
            },
            "repetition": 1,
        },
    ],
    "config_hash": "config-hash-plan",
    "migration_warnings": [],
    "same_start_snapshot": None,
    "replay_canonical": None,
    "denominator_policy": "include_failed",
}

# ---------------------------------------------------------------------------
# Legacy v0.1.x variant — raw dict literal (old format, cannot be produced by
# current Pydantic models; kept as-is for backward-compat testing)
# ---------------------------------------------------------------------------

RUN_LEGACY_V01X: dict = {  # type: ignore[type-arg]
    "schema_version": "1.0",
    "id": "run-legacy-v01",
    "project_name": "legacy-project",
    "status": "completed",
    "created_at": "2026-05-01T00:00:00+00:00",
    "completed_at": "2026-05-01T00:01:00+00:00",
    "failure_reason": None,
    "output_dir": ".micro-eval/runs",
    "config_hash": "config-hash-legacy",
    "tasks": ["task-1"],
    "configurations": ["baseline", "candidate"],
    "cells": ["cell-1", "cell-2"],
    "results": [
        {
            "schema_version": "1.0",
            "cell_id": "cell-1",
            "run_id": "run-legacy-v01",
            "task_id": "task-1",
            "configuration_id": "baseline",
            "configuration_name": "Baseline",
            "repetition": 1,
            "status": "pass",
            "score": 1.0,
            "pass_fail": "pass",
            "output_summary": "ok",
            "stdout_summary": "ok",
            "stderr_summary": "",
            "exit_code": 0,
            "latency_s": 0.1,
            "failure_mode": None,
            "artifact_refs": [],
            "evidence_refs": [],
            "evaluation_refs": [],
            "trace_refs": [],
            "cell_snapshot": None,
            "snapshot_gate_result": None,
        },
        {
            "schema_version": "1.0",
            "cell_id": "cell-2",
            "run_id": "run-legacy-v01",
            "task_id": "task-1",
            "configuration_id": "candidate",
            "configuration_name": "Candidate",
            "repetition": 1,
            "status": "fail",
            "score": 0.0,
            "pass_fail": "fail",
            "output_summary": "fail",
            "stdout_summary": "wrong",
            "stderr_summary": "",
            "exit_code": 0,
            "latency_s": 0.2,
            "failure_mode": None,
            "artifact_refs": [],
            "evidence_refs": [],
            "evaluation_refs": [],
            "trace_refs": [],
            "cell_snapshot": None,
            "snapshot_gate_result": None,
        },
    ],
    "migration_warnings": [],
    "same_start_snapshot": None,
    "replay_canonical": None,
    "artifacts": [],
    "evidence": [],
    "traces": [],
    "evaluations": [],
    "decision": {
        "schema_version": "1.0",
        "decision_report_id": "",
        "verdict": "regressed",
        "confidence": "low",
        "evaluation_refs": [],
        "evidence_refs": [],
        "caveats": ["low sample size for baseline: repetitions < 3"],
        # Legacy aggregation format — no per_configuration wrapper, uses total/passed/failed
        "aggregation": {
            "schema_version": "1.0",
            "baseline": {
                "schema_version": "1.0",
                "total": 1,
                "passed": 1,
                "failed": 0,
                "pass_rate": 1.0,
                "mean_latency_ms": 100.0,
            },
            "candidate": {
                "schema_version": "1.0",
                "total": 1,
                "passed": 0,
                "failed": 1,
                "pass_rate": 0.0,
                "mean_latency_ms": 200.0,
            },
        },
        "recommended_action": "review evidence",
        "timestamp": "20260501T000000Z",
        "created_at": "20260501T000000Z",
    },
}


# ---------------------------------------------------------------------------
# Decision algorithm equivalence fixture (issue #1)
#
# The UI `recomputeDecision` (ui/src/lib/evaluation.ts) hand-mirrors the Python
# `build_decision` algorithm. The schema golden only protects shape, not
# algorithmic equivalence. This fixture pins one canonical input run together
# with the decision the *Python* algorithm produces for it, so the vitest
# contract can feed the same input to `recomputeDecision` and assert an
# identical (normalised) decision. Time-dependent fields are stripped and all
# floats are rounded so the comparison is deterministic across languages.
# ---------------------------------------------------------------------------

FLOAT_ROUND_DIGITS = 12


def _round_floats(value):  # type: ignore[no-untyped-def]
    """Recursively round floats so cross-language float noise does not break equality."""
    if isinstance(value, float):
        return round(value, FLOAT_ROUND_DIGITS)
    if isinstance(value, dict):
        return {key: _round_floats(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_round_floats(item) for item in value]
    return value


def normalize_decision(decision: dict) -> dict:  # type: ignore[type-arg]
    """Strip time-dependent fields and round floats for equivalence comparison."""
    normalized = dict(decision)
    normalized.pop("decision_report_id", None)
    normalized.pop("timestamp", None)
    normalized.pop("created_at", None)
    return _round_floats(normalized)


def _equiv_result(
    *,
    cell_id: str,
    configuration_id: str,
    configuration_name: str,
    repetition: int,
    status: str,
    pass_fail: str | None,
    latency_s: float,
) -> dict:  # type: ignore[type-arg]
    """Build a minimal CellResult dict carrying evaluation/evidence refs."""
    return {
        "schema_version": "1.0",
        "cell_id": cell_id,
        "run_id": "run-decision-equivalence",
        "task_id": "task-eq",
        "configuration_id": configuration_id,
        "configuration_name": configuration_name,
        "repetition": repetition,
        "status": status,
        "score": 1.0 if pass_fail == "pass" else 0.0,
        "pass_fail": pass_fail,
        "output_summary": status,
        "stdout_summary": status,
        "stderr_summary": "",
        "exit_code": 0,
        "latency_s": latency_s,
        "failure_mode": None,
        "artifact_refs": [],
        "evidence_refs": [f"{cell_id}::evidence::process"],
        "evaluation_refs": [f"{cell_id}::validator::eq"],
        "trace_refs": [f"process:{cell_id}"],
        "cell_snapshot": None,
        "snapshot_gate_result": None,
    }


def _equiv_trace(cell_id: str, amount: float | None, source: str) -> dict:  # type: ignore[type-arg]
    """Build a TraceRef dict matched to a cell by trace_id == cell_id."""
    return {
        "schema_version": "1.0",
        "trace_id": cell_id,
        "provider": "langfuse",
        "external_url": None,
        "cost": {"schema_version": "1.0", "amount": amount, "currency": "USD", "source": source},
        "summary": {},
    }


# Two configurations: `baseline` (3 successful cells, real trace costs, not
# low_sample) and `candidate` (1 fail + 1 error, low_sample, one null-cost
# trace) — exercises cost aggregation, denominator/pass_rate, pass@k/pass^k,
# low_sample caveats, and same-start caveat merging in a single input.
DECISION_EQUIVALENCE_RUN: dict = {  # type: ignore[type-arg]
    "schema_version": "1.0",
    "id": "run-decision-equivalence",
    "project_name": "decision-equivalence",
    "status": "completed",
    "created_at": "2026-06-14T00:00:00+00:00",
    "completed_at": "2026-06-14T00:01:00+00:00",
    "failure_reason": None,
    "output_dir": ".micro-eval/runs",
    "config_hash": "config-hash-eq",
    "tasks": ["task-eq"],
    "configurations": ["baseline", "candidate"],
    "cells": ["cell-b1", "cell-b2", "cell-b3", "cell-c1", "cell-c2"],
    "results": [
        _equiv_result(cell_id="cell-b1", configuration_id="baseline", configuration_name="Baseline", repetition=1, status="pass", pass_fail="pass", latency_s=0.1),
        _equiv_result(cell_id="cell-b2", configuration_id="baseline", configuration_name="Baseline", repetition=2, status="pass", pass_fail="pass", latency_s=0.2),
        _equiv_result(cell_id="cell-b3", configuration_id="baseline", configuration_name="Baseline", repetition=3, status="fail", pass_fail="fail", latency_s=0.3),
        _equiv_result(cell_id="cell-c1", configuration_id="candidate", configuration_name="Candidate", repetition=1, status="fail", pass_fail="fail", latency_s=0.15),
        _equiv_result(cell_id="cell-c2", configuration_id="candidate", configuration_name="Candidate", repetition=2, status="error", pass_fail=None, latency_s=0.0),
    ],
    "migration_warnings": [],
    "same_start_snapshot": {
        "schema_version": "1.0",
        "workspace_type": "blank",
        "git_commit": None,
        "dirty": None,
        "config_hash": "config-hash-eq",
        "configuration_digests": {"baseline": "digest-b", "candidate": "digest-c"},
        "task_revisions": {"task-eq": "revision-eq"},
        "python_version": "3.11.0",
        "setup_commands_digest": None,
        "guardrails_digest": "guardrails-eq",
        "sandbox_resource_limits": None,
        "workspace_map": None,
        "timestamp": "2026-06-14T00:00:00+00:00",
        "caveats": ["example same-start caveat"],
    },
    "replay_canonical": None,
    "artifacts": [],
    "evidence": [],
    "traces": [
        _equiv_trace("cell-b1", 0.01, "langfuse"),
        _equiv_trace("cell-b2", 0.02, "langfuse"),
        _equiv_trace("cell-b3", None, "unavailable"),
        _equiv_trace("cell-c1", 0.05, "langfuse"),
    ],
    "evaluations": [],
    "denominator_policy": "include_failed",
    "decision": None,
}


def _write_decision_equivalence_fixture() -> None:
    """Pin the Python decision output for the canonical equivalence input run."""
    record = RunRecord.model_validate(DECISION_EQUIVALENCE_RUN)
    decision = build_decision(record)
    expected = normalize_decision(decision.model_dump(mode="json"))
    # Store the canonical (model_dump) form of the run so the zod schema accepts
    # it verbatim, alongside the normalised Python decision.
    payload = {
        "run": _round_floats(record.model_dump(mode="json")),
        "expected_decision": expected,
    }
    _write("decision-equivalence.json", payload)


def generate_all() -> None:
    """Write all golden fixtures."""
    print("Generating golden fixtures...")

    _write("run-phase2-full.json", RUN_PHASE2_FULL)
    _write("run-minimal.json", RUN_MINIMAL)
    _write("decision-report.json", DECISION_REPORT)
    _write("trace-ref.json", TRACE_REF)
    _write("evaluation-result.json", EVALUATION_RESULT)
    _write("run-plan.json", RUN_PLAN)
    _write("run-legacy-v01x.json", RUN_LEGACY_V01X)
    _write_decision_equivalence_fixture()

    # Write canonical-run-p0.json to its original path for check-version-consistency.py.
    # This is the P0 fixture that the release preflight script reads tool_version from.
    # Content is identical to canonical-run-p0.json produced by test_contract_fixture.py
    # assertions (id=run-contract-fixture, replay_canonical.tool_version must match VERSION).
    _write_p0_fixture()

    print("Done.")


def _write_p0_fixture() -> None:
    """Write canonical-run-p0.json to ui/src/lib/fixtures/ for release preflight."""
    # Read current VERSION to keep tool_version in sync.
    version_path = REPO_ROOT / "VERSION"
    tool_version = version_path.read_text(encoding="utf-8").strip()

    p0_data: dict = {  # type: ignore[type-arg]
        "schema_version": "1.0",
        "id": "run-contract-fixture",
        "project_name": "contract-fixture",
        "status": "completed",
        "created_at": "2026-06-02T00:00:00+00:00",
        "completed_at": "2026-06-02T00:00:01+00:00",
        "failure_reason": None,
        "output_dir": ".micro-eval/runs",
        "config_hash": "config-hash",
        "tasks": ["task-1"],
        "configurations": ["baseline", "candidate"],
        "cells": ["cell-1"],
        "results": [
            {
                "schema_version": "1.0",
                "cell_id": "cell-1",
                "run_id": "run-contract-fixture",
                "task_id": "task-1",
                "configuration_id": "baseline",
                "configuration_name": "Baseline",
                "repetition": 1,
                "status": "pass",
                "score": 1.0,
                "pass_fail": "pass",
                "output_summary": "ok",
                "stdout_summary": "ok",
                "stderr_summary": "",
                "exit_code": 0,
                "latency_s": 0.1,
                "failure_mode": None,
                "artifact_refs": ["cell-1::stdout::abc123"],
                "evidence_refs": ["cell-1::evidence::process"],
                "evaluation_refs": ["cell-1::validator::abc123"],
                "trace_refs": [],
                "cell_snapshot": {
                    "schema_version": "1.0",
                    "workspace_path": "/tmp/workspace",
                    "git_commit": None,
                    "dirty": None,
                    "setup_exit_code": None,
                    "timestamp": "2026-06-02T00:00:00+00:00",
                    "cleanup_status": "cleaned",
                    "cleanup_error": None,
                },
                "snapshot_gate_result": {
                    "schema_version": "1.0",
                    "status": "pass",
                    "mismatch_fields": [],
                    "gate_version": "1.0",
                    "caveats": [],
                },
            },
        ],
        "migration_warnings": [],
        "same_start_snapshot": {
            "schema_version": "1.0",
            "workspace_type": "blank",
            "git_commit": None,
            "dirty": None,
            "config_hash": "config-hash",
            "configuration_digests": {"baseline": "digest-a", "candidate": "digest-b"},
            "task_revisions": {"task-1": "revision-a"},
            "python_version": "3.11.0",
            "setup_commands_digest": None,
            "guardrails_digest": "guardrails-digest",
            "sandbox_resource_limits": None,
            "workspace_map": None,
            "timestamp": "2026-06-02T00:00:00+00:00",
            "caveats": [],
        },
        "replay_canonical": {
            "schema_version": "1.0",
            "tool_version": tool_version,
            "config_hash": "config-hash",
            "task_ids": ["task-1"],
            "task_revisions": {"task-1": "revision-a"},
            "configuration_ids": ["baseline", "candidate"],
            "configuration_digests": {"baseline": "digest-a", "candidate": "digest-b"},
            "workspace_type": "blank",
            "git_commit": None,
            "workspace_map": None,
            "workspace_fingerprint": "workspace-fingerprint",
            "setup_commands_digest": None,
            "guardrails_digest": "guardrails-digest",
            "max_concurrency": 2,
            "digest": "replay-digest",
        },
        "artifacts": [
            {
                "schema_version": "1.0",
                "artifact_id": "cell-1::stdout::abc123",
                "kind": "stdout",
                "path": "cells/cell-1/stdout.txt",
                "sha256": "abc123",
                "size_bytes": 2,
                "media_type": "text/plain",
                "redacted": True,
                "warning": None,
            },
        ],
        "evidence": [
            {
                "schema_version": "1.0",
                "evidence_id": "cell-1::evidence::process",
                "kind": "process",
                "summary": "status=pass exit_code=0",
                "source_kind": "artifact_ref",
                "source_ref": "cell-1::stdout::abc123",
                "cell_id": "cell-1",
                "status": "passed",
                "severity": "info",
                "artifact_refs": ["cell-1::stdout::abc123"],
                "metadata": {"exit_code": 0},
            },
        ],
        "traces": [],
        "evaluations": [
            {
                "schema_version": "1.0",
                "evaluation_id": "cell-1::validator::abc123",
                "cell_id": "cell-1",
                "evaluator_type": "validator",
                "evaluator": "micro-eval-deterministic-validator",
                "pass_fail": "pass",
                "score": 1.0,
                "scores": {},
                "evaluator_meta": None,
                "rubric_hash": None,
                "comment": "ok",
                "evidence_refs": ["cell-1::evidence::process"],
                "created_at": "20260602T000000Z",
            },
        ],
        "decision": {
            "schema_version": "1.0",
            "decision_report_id": "run-contract-fixture::decision::20260602T000000Z",
            "verdict": "inconclusive",
            "confidence": "low",
            "evaluation_refs": ["cell-1::validator::abc123"],
            "evidence_refs": ["cell-1::evidence::process"],
            "caveats": ["low sample size for baseline: repetitions < 3"],
            "aggregation": {
                "schema_version": "1.0",
                "per_configuration": {
                    "baseline": {
                        "schema_version": "1.0",
                        "n_cells": 1,
                        "n_successful": 1,
                        "pass_rate": 1.0,
                        "pass_at_k": {"1": 1.0},
                        "pass_hat_k": {"1": 1.0},
                        "mean_latency_ms": 100.0,
                        "median_latency_ms": 100.0,
                        "total_cost": None,
                        "denominator_policy": "include_failed",
                        "caveats": ["low_sample"],
                    },
                },
            },
            "timestamp": "20260602T000000Z",
            "recommended_action": "review evidence",
            "created_at": "20260602T000000Z",
        },
    }

    # Write to the original location (no trailing newline difference)
    p0_path = REPO_ROOT / "ui" / "src" / "lib" / "fixtures" / "canonical-run-p0.json"
    p0_path.write_text(json.dumps(p0_data, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {p0_path.relative_to(REPO_ROOT)}")

    # Also write a copy into golden/ so the golden-sync diff covers it
    golden_p0_path = GOLDEN_DIR / "run-p0-contract.json"
    golden_p0_path.write_text(json.dumps(p0_data, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {golden_p0_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    generate_all()
    sys.exit(0)
