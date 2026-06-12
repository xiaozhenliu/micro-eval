"""Contract golden fixture tests.

Covers:
- Pydantic round-trip for all golden JSON files
- Idempotency: re-generating goldens produces byte-identical output
- Security assertions: no secret strings, no absolute home paths
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from micro_eval.models.artifact import TraceRef
from micro_eval.models.decision import DecisionReport
from micro_eval.models.evaluation import EvaluationResult
from micro_eval.models.run import RunPlan, RunRecord

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GOLDEN_DIR = REPO_ROOT / "tests" / "contract" / "golden"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _golden(name: str) -> Path:
    return GOLDEN_DIR / name


def _load(name: str) -> dict:  # type: ignore[type-arg]
    return json.loads(_golden(name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Pydantic round-trip tests
# ---------------------------------------------------------------------------


def test_run_phase2_full_roundtrip() -> None:
    """Phase 2 RunRecord with all optional fields populated parses correctly."""
    data = _load("run-phase2-full.json")
    record = RunRecord.model_validate(data)

    assert record.id == "run-phase2-fixture"
    assert record.traces and record.traces[0].provider in {"process", "langfuse"}
    any_llm = any(e.evaluator_type == "llm_judge" for e in record.evaluations)
    assert any_llm, "expected at least one llm_judge evaluation"
    assert record.decision is not None
    assert record.decision.decision_report_id
    assert all(
        stats.denominator_policy for stats in record.decision.aggregation.per_configuration.values()
    )


def test_run_minimal_roundtrip() -> None:
    """RunRecord with all optional fields null/empty parses correctly."""
    data = _load("run-minimal.json")
    record = RunRecord.model_validate(data)

    assert record.id == "run-minimal-fixture"
    assert record.same_start_snapshot is None
    assert record.replay_canonical is None
    assert record.decision is None
    assert record.traces == []
    assert record.evaluations == []


def test_decision_report_roundtrip() -> None:
    """Standalone DecisionReport parses correctly."""
    data = _load("decision-report.json")
    report = DecisionReport.model_validate(data)

    assert report.decision_report_id
    assert report.aggregation.per_configuration


def test_trace_ref_roundtrip() -> None:
    """Standalone TraceRef parses correctly."""
    data = _load("trace-ref.json")
    trace = TraceRef.model_validate(data)

    assert trace.trace_id == "cell-b1"
    assert trace.provider == "langfuse"
    assert trace.cost is not None


def test_evaluation_result_roundtrip() -> None:
    """Standalone EvaluationResult parses correctly."""
    data = _load("evaluation-result.json")
    result = EvaluationResult.model_validate(data)

    assert result.evaluator_type == "llm_judge"
    assert result.rubric_hash is not None


def test_run_plan_roundtrip() -> None:
    """RunPlan parses correctly."""
    data = _load("run-plan.json")
    plan = RunPlan.model_validate(data)

    assert plan.run_id == "run-plan-fixture"
    assert len(plan.cells) == 1


def test_run_legacy_v01x_compat() -> None:
    """Legacy v0.1.x format is accepted by RunRecord (backward compat)."""
    data = _load("run-legacy-v01x.json")
    record = RunRecord.model_validate(data)

    assert record.id == "run-legacy-v01"
    assert record.decision is not None
    assert record.decision.verdict.value == "regressed"
    baseline = record.decision.aggregation.per_configuration.get("baseline")
    assert baseline is not None
    assert baseline.pass_rate == 1.0


def test_run_p0_contract_roundtrip() -> None:
    """P0 contract fixture (used by release preflight) parses correctly."""
    data = _load("run-p0-contract.json")
    record = RunRecord.model_validate(data)

    assert record.id == "run-contract-fixture"
    assert record.same_start_snapshot is not None
    assert record.replay_canonical is not None
    assert record.results[0].cell_snapshot is not None
    assert record.results[0].snapshot_gate_result is not None


# ---------------------------------------------------------------------------
# Idempotency test
# ---------------------------------------------------------------------------


def test_golden_generation_is_idempotent(tmp_path: Path) -> None:
    """Re-running generate-golden.py produces byte-identical output."""
    import importlib.util
    import shutil

    # Capture current golden contents
    original_files = {p.name: p.read_bytes() for p in GOLDEN_DIR.glob("*.json")}

    # Run the generator script in a subprocess to avoid module caching issues
    generate_script = REPO_ROOT / "scripts" / "generate-golden.py"
    result = subprocess.run(
        [sys.executable, str(generate_script)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"generate-golden.py failed:\n{result.stderr}"

    # Compare every golden file
    for name, original_bytes in original_files.items():
        regenerated = (GOLDEN_DIR / name).read_bytes()
        assert regenerated == original_bytes, (
            f"Golden file '{name}' changed after re-generation — "
            "the generator is not idempotent. Run scripts/generate-golden.py and commit."
        )

    # Ensure no new files were silently added
    new_files = {p.name for p in GOLDEN_DIR.glob("*.json")}
    assert new_files == set(original_files.keys()), (
        f"Generator produced unexpected new files: {new_files - set(original_files.keys())}"
    )


# ---------------------------------------------------------------------------
# Security assertions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("golden_file", list(GOLDEN_DIR.glob("*.json")))
def test_golden_no_secret_strings(golden_file: Path) -> None:
    """Golden files must not contain the MICRO_EVAL_SECRET placeholder."""
    content = golden_file.read_text(encoding="utf-8")
    assert "MICRO_EVAL_SECRET" not in content, (
        f"{golden_file.name} contains forbidden string 'MICRO_EVAL_SECRET'"
    )


@pytest.mark.parametrize("golden_file", list(GOLDEN_DIR.glob("*.json")))
def test_golden_no_home_paths(golden_file: Path) -> None:
    """Golden files must not contain absolute home directory paths."""
    content = golden_file.read_text(encoding="utf-8")
    # Check for common home path prefixes that could leak user identity
    for forbidden_prefix in ("/Users/", "/home/"):
        # Allow /tmp/ but not /Users/ or /home/
        assert forbidden_prefix not in content, (
            f"{golden_file.name} contains a home directory path starting with '{forbidden_prefix}'. "
            "Golden fixtures must not leak local filesystem paths."
        )
