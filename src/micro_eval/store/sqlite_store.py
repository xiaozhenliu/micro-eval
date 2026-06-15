"""SQLite-backed store for cross-run queries and trend analysis.

Provides an indexed view over run data while preserving JSON as the source of
truth for run details. Existing JSON runs can be imported; new runs are indexed
on finalization. The SQLite DB is a derived cache — it can always be rebuilt
from the JSON files.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from micro_eval.models.decision import DecisionReport
from micro_eval.models.run import RunRecord

SCHEMA_VERSION = 1

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    project_name TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    config_hash TEXT,
    output_dir TEXT NOT NULL,
    verdict TEXT,
    confidence TEXT,
    json_path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_configurations (
    run_id TEXT NOT NULL,
    configuration_id TEXT NOT NULL,
    pass_rate REAL,
    mean_latency_ms REAL,
    total_cost_amount REAL,
    n_cells INTEGER DEFAULT 0,
    PRIMARY KEY (run_id, configuration_id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_run_config_id ON run_configurations(configuration_id);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at);
"""


class SqliteStore:
    """Cross-run query layer backed by SQLite."""

    def __init__(self, project_root: Path | str, db_name: str = ".micro-eval/index.db") -> None:
        self._project_root = Path(project_root).resolve()
        self._db_path = self._project_root / db_name
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.executescript(_SCHEMA_SQL)
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            self._conn.commit()

    def index_run(self, record: RunRecord, json_path: str | None = None) -> None:
        """Index a finalized run into SQLite."""
        verdict = record.decision.verdict if record.decision else None
        confidence = record.decision.confidence if record.decision else None
        path = json_path or f"{record.output_dir}/{record.id}/run.json"

        self._conn.execute(
            """\
            INSERT OR REPLACE INTO runs
            (run_id, project_name, status, created_at, completed_at,
             config_hash, output_dir, verdict, confidence, json_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id,
                record.project_name,
                record.status.value if hasattr(record.status, "value") else record.status,
                record.created_at,
                record.completed_at,
                record.config_hash,
                record.output_dir,
                verdict,
                confidence,
                path,
            ),
        )

        self._conn.execute(
            "DELETE FROM run_configurations WHERE run_id = ?", (record.id,)
        )
        if record.decision and record.decision.aggregation:
            for config_id, stats in record.decision.aggregation.per_configuration.items():
                cost_amount = None
                if stats.total_cost and stats.total_cost.amount is not None:
                    cost_amount = stats.total_cost.amount
                self._conn.execute(
                    """\
                    INSERT INTO run_configurations
                    (run_id, configuration_id, pass_rate, mean_latency_ms, total_cost_amount, n_cells)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        record.id,
                        config_id,
                        stats.pass_rate,
                        stats.mean_latency_ms,
                        cost_amount,
                        stats.n_cells,
                    ),
                )
        self._conn.commit()

    def import_json_runs(self, output_dir: str = ".micro-eval/runs") -> int:
        """Import all JSON runs into SQLite. Returns count of imported runs."""
        runs_dir = self._project_root / output_dir
        if not runs_dir.exists():
            return 0
        count = 0
        for path in sorted(runs_dir.iterdir()):
            run_json = path / "run.json"
            if not path.is_dir() or not run_json.exists():
                continue
            try:
                record = RunRecord.model_validate_json(run_json.read_text())
                decision_json = path / "decision.json"
                if decision_json.exists():
                    record.decision = DecisionReport.model_validate_json(
                        decision_json.read_text()
                    )
                rel_path = str(run_json.relative_to(self._project_root))
                self.index_run(record, json_path=rel_path)
                count += 1
            except Exception:
                continue
        return count

    def trend_series(
        self, configuration_id: str, *, metric: str = "pass_rate", limit: int = 50
    ) -> list[dict]:
        """Return a time-ordered series of a metric for one configuration.

        Each entry: {run_id, created_at, value, verdict, confidence, drift_break}.
        drift_break is True when configuration content changed between consecutive runs.
        """
        rows = self._conn.execute(
            """\
            SELECT r.run_id, r.created_at, r.verdict, r.confidence, r.config_hash,
                   rc.pass_rate, rc.mean_latency_ms, rc.total_cost_amount, rc.n_cells
            FROM run_configurations rc
            JOIN runs r ON rc.run_id = r.run_id
            WHERE rc.configuration_id = ?
            ORDER BY r.created_at ASC
            LIMIT ?""",
            (configuration_id, limit),
        ).fetchall()

        series: list[dict] = []
        prev_hash: str | None = None
        for row in rows:
            value = row[metric] if metric in ("pass_rate", "mean_latency_ms", "total_cost_amount", "n_cells") else row["pass_rate"]
            drift_break = prev_hash is not None and row["config_hash"] != prev_hash
            series.append({
                "run_id": row["run_id"],
                "created_at": row["created_at"],
                "value": value,
                "verdict": row["verdict"],
                "confidence": row["confidence"],
                "drift_break": drift_break,
            })
            prev_hash = row["config_hash"]
        return series

    def configuration_ids(self) -> list[str]:
        """Return all known configuration IDs."""
        rows = self._conn.execute(
            "SELECT DISTINCT configuration_id FROM run_configurations ORDER BY configuration_id"
        ).fetchall()
        return [row["configuration_id"] for row in rows]

    def close(self) -> None:
        self._conn.close()
