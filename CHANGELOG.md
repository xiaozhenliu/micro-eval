# Changelog

All notable changes to `micro-eval` are documented here.

## 0.1.1 - 2026-06-02

### Added

- Capture agent invocation evidence for each `RunResult`: stdout summary/ref, stderr summary/ref, exit code, output directory, and output artifact refs.
- Store invocation artifacts under `.micro-eval/artifacts/{run_id}/{task_id}--{agent_name}/`.
- Add bounded stdout/stderr capture with a 10 MB retained-output cap.
- Add environment allowlisting for subprocess execution and pass `MICRO_EVAL_OUTPUT_DIR` / `MICRO_EVAL_OUTPUT_FILE` to agents.
- Add focused runner and schema coverage for evidence fields, file/directory output artifacts, timeout handling, and secret redaction from agent environment values.

### Changed

- Replace shell-based agent execution with `asyncio.create_subprocess_exec` and argv construction via `shlex.split`.
- Keep stdout/stderr/output summaries as bounded excerpts while preserving full retained artifacts on disk.
- Align the TypeScript zod schema with the new Python `RunResult` evidence fields.

### Known Gaps

- The run storage format is still the legacy flat `.micro-eval/runs/{run_id}.json` shape, not the full MVP `runs/{run_id}/run.json + manifest.json + cells/` layout.
- Configuration matrix, RunPlan/RunCell, SameStartSnapshot/CellSnapshot, ArtifactRef/EvidenceItem, and persisted `evaluation.json` are still future P0/P1 work.
- Artifact paths can still collide if baseline and candidate use the same `agent_name`; fix this before moving into P0-a/P0-b work.
- UI lint still fails on the existing `AnnotationPanel` localStorage hydration effect.

## 0.1.0 - 2026-06-02

### Added

- Initial local CLI and Next.js Web UI MVP.
- Baseline/candidate pairwise evaluation with YAML config and task files.
- Async subprocess runner, exact/contains scoring, JSON run output, HTML report generation, and basic run list/comparison UI.
