"""ISSUE-3: Legacy v0.1.x run compatibility — fixed fixture regression guard.

Acceptance criteria:
- v0.1.x run.json (decision embedded, no decision.json, no Phase 2 fields)
  can be read by RunStore.list_runs / read_run without error
- decision verdict comes from run.json["decision"]
- CLI `micro-eval report --run <id>` exits 0 and produces output
- TS zod schema can parse the same fixture (tested in ISSUE-1 test file)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from micro_eval.models.run import RunRecord
from micro_eval.store.run_store import RunStore

# Path to the committed v0.1.x fixture
LEGACY_FIXTURE = Path(__file__).parent.parent / "fixtures" / "legacy" / "run-v01x-embedded-decision.json"


def test_legacy_fixture_parses_with_pydantic() -> None:
    """Pydantic must accept the v0.1.x run.json format without error."""
    record = RunRecord.model_validate_json(LEGACY_FIXTURE.read_text())
    assert record.id == "run-legacy-v01"
    assert record.decision is not None
    assert record.decision.verdict.value == "regressed"


def test_legacy_fixture_decision_comes_from_embedded_json() -> None:
    """Verdict must be read from the embedded run.json['decision'], not from a
    separate decision.json (which does not exist for this fixture)."""
    record = RunRecord.model_validate_json(LEGACY_FIXTURE.read_text())
    # No separate decision.json exists alongside this fixture — decision is embedded
    assert record.decision is not None
    assert record.decision.verdict.value == "regressed"
    # aggregation must survive legacy stats migration
    baseline_stats = record.decision.aggregation.per_configuration.get("baseline")
    assert baseline_stats is not None
    assert baseline_stats.pass_rate == 1.0


def test_run_store_list_runs_returns_legacy_run(tmp_path: Path) -> None:
    """RunStore.list_runs must return the legacy run without throwing."""
    # Set up .micro-eval/runs/<id>/ directory using the legacy fixture
    run_id = "run-legacy-v01"
    run_dir = tmp_path / ".micro-eval" / "runs" / run_id
    run_dir.mkdir(parents=True)
    import shutil
    shutil.copy(LEGACY_FIXTURE, run_dir / "run.json")
    # No decision.json — legacy format has it embedded

    store = RunStore(project_root=tmp_path)
    runs = store.list_runs()

    assert len(runs) == 1
    run = runs[0]
    assert isinstance(run, RunRecord)
    assert run.id == run_id
    assert run.decision is not None
    assert run.decision.verdict.value == "regressed"


def test_cli_report_consumes_legacy_run(tmp_path: Path) -> None:
    """CLI `micro-eval report --run <id>` must exit 0 for a legacy run."""
    run_id = "run-legacy-v01"
    run_dir = tmp_path / ".micro-eval" / "runs" / run_id
    run_dir.mkdir(parents=True)
    import shutil
    shutil.copy(LEGACY_FIXTURE, run_dir / "run.json")

    result = subprocess.run(
        [sys.executable, "-m", "micro_eval.cli.main", "report", "--run", run_id, "--format", "json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"report failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    data = json.loads(result.stdout)
    assert data["id"] == run_id
    assert data["decision"]["verdict"] == "regressed"
