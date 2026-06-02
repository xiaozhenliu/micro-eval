# Changelog

All notable changes to `micro-eval` are documented here.

## 0.1.2 - 2026-06-02

### Changed

- Generate run IDs as `run-YYYYMMDDTHHMMSSZ-<random8>` for readable, collision-resistant legacy run files.
- Add baseline/candidate role labels to invocation artifact paths so same-name baseline and candidate agents no longer overwrite each other's stdout, stderr, or output directory.
- Keep the legacy flat `.micro-eval/runs/{run_id}.json` shape unchanged while hardening artifact references.

### Fixed

- Fix `AnnotationPanel` localStorage hydration so `cd ui && npm run lint` passes without changing the annotation save/export workflow.
- Add regression coverage for same-name agent artifact paths, distinct run IDs, readable stdout/stderr refs, file and directory output artifact capture, secret redaction, and timeout handling.

### Known Gaps

- The run storage format is still the legacy flat `.micro-eval/runs/{run_id}.json` shape, not the full MVP `runs/{run_id}/run.json + manifest.json + cells/` layout.
- Configuration matrix, RunPlan/RunCell, SameStartSnapshot/CellSnapshot, ArtifactRef/EvidenceItem, and persisted `evaluation.json` are still future P0/P1 work.
- Annotation data remains localStorage-backed UI state, not persisted human scoring.

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

## 0.1.0 - 2026-06-02

### Added

- Initial local CLI and Next.js Web UI MVP.
- Baseline/candidate pairwise evaluation with YAML config and task files.
- Async subprocess runner, exact/contains scoring, JSON run output, HTML report generation, and basic run list/comparison UI.
