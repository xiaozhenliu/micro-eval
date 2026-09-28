"""Cross-run configuration comparability caveats (issue #2).

A configuration id is the identity used to compare runs. When its content (its
recorded digest) changes under a reused id, results across runs are no longer
directly comparable; the store surfaces a caveat instead of comparing silently.
"""

from __future__ import annotations

from pathlib import Path

from micro_eval.models.environment import SameStartSnapshot
from micro_eval.models.run import RunRecord
from micro_eval.store.run_store import RunStore


def _record(run_id: str, created_at: str, digests: dict[str, str]) -> RunRecord:
    return RunRecord(
        id=run_id,
        project_name="proj",
        created_at=created_at,
        output_dir=".micro-eval/runs",
        same_start_snapshot=SameStartSnapshot(configuration_digests=digests),
    )


def test_drift_caveat_when_config_content_changes(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.write_run(_record("run-old", "2026-06-10T08:00:00Z", {"baseline": "AAA11111"}))
    current = _record("run-new", "2026-06-12T08:00:00Z", {"baseline": "BBB22222"})

    caveats = store.configuration_drift_caveats(current)

    assert len(caveats) == 1
    assert "baseline" in caveats[0]
    assert "run-old" in caveats[0]
    assert "not be comparable" in caveats[0]


def test_no_caveat_when_digest_unchanged(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.write_run(_record("run-old", "2026-06-10T08:00:00Z", {"baseline": "AAA11111"}))
    current = _record("run-new", "2026-06-12T08:00:00Z", {"baseline": "AAA11111"})

    assert store.configuration_drift_caveats(current) == []


def test_no_caveat_for_new_configuration_id(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.write_run(_record("run-old", "2026-06-10T08:00:00Z", {"baseline": "AAA11111"}))
    current = _record("run-new", "2026-06-12T08:00:00Z", {"candidate": "CCC33333"})

    assert store.configuration_drift_caveats(current) == []


def test_no_caveat_without_prior_runs(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    current = _record("run-first", "2026-06-12T08:00:00Z", {"baseline": "AAA11111"})

    assert store.configuration_drift_caveats(current) == []


def test_compares_against_most_recent_prior_only(tmp_path: Path) -> None:
    # Oldest prior matches the current digest, but the most recent prior differs.
    # The check must compare against the most recent prior with that id only, so a
    # caveat is produced and it names the most recent prior run.
    store = RunStore(tmp_path)
    store.write_run(_record("run-oldest", "2026-06-08T08:00:00Z", {"baseline": "AAA11111"}))
    store.write_run(_record("run-mid", "2026-06-10T08:00:00Z", {"baseline": "BBB22222"}))
    current = _record("run-new", "2026-06-12T08:00:00Z", {"baseline": "AAA11111"})

    caveats = store.configuration_drift_caveats(current)

    assert len(caveats) == 1
    assert "run-mid" in caveats[0]


def test_no_snapshot_returns_empty(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    record = RunRecord(
        id="r", project_name="proj", created_at="2026-06-12T08:00:00Z", output_dir=".micro-eval/runs"
    )
    assert store.configuration_drift_caveats(record) == []
