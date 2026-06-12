# Changelog

All notable changes to `micro-eval` are documented here.

## 0.2.1 - 2026-06-12

### Added

- Update the examples to surface Phase 2: the deterministic mock path now runs 3 repetitions with process trace capture (real pass@k/pass^k in reports and decision.json), example configs document optional `trace:`/`judge:` blocks, and the READMEs explain the Phase 2 review surfaces.

- Add cross-language API route contract tests: Python-generated Phase 2 fixtures (run + decision) consumed by both pytest (Pydantic) and vitest (zod), guarding the `.micro-eval/` JSON boundary.
- Add a Phase 2 golden-path e2e covering trace + mock judge + decision.json + report cost source in one flow, including the judge-cannot-override-deterministic-failure contract.
- Add a frozen v0.1.x legacy run fixture with compatibility tests on both the Python store/CLI side and the UI zod schema side.
- Add CLI failure-path e2e tests asserting non-zero exit codes and error messages for invalid config, unknown run id, and malformed YAML.
- Add Decision Surface honesty assertions: `not_comparable` runs render no winner marker; `low_sample` caveats are visible.
- Add unit tests closing coverage gaps in the Langfuse provider (degradation, cost ladder, redaction), deterministic validator (path-escape, command, redaction branches), and run store boundaries (root escape, legacy fallback).

## 0.2.0 - 2026-06-12

### Added

- Add Phase 2 aggregation with per-configuration `ConfigurationStats`, pass@k, pass^k, latency summaries, low-sample caveats, and `CostMetric` source metadata.
- Persist guarded decisions as sibling `.micro-eval/runs/{run_id}/decision.json` while preserving legacy embedded-decision read compatibility.
- Add optional trace capture through `TraceProvider`, a process fallback provider, optional Langfuse adapter, manifest `TraceRef` records, and per-cell trace references.
- Add a Phase 2 review UI at `/run/[id]/review` with cost, trace, matrix heatmap, and per-cell evidence panels.
- Add an optional default-off LLM judge path with DeepEval adapter plumbing, `EvaluationResult.evaluator_meta`, `rubric_hash`, and supplemental judge evidence.
- Add development decision notes and logs for aggregation, trace collection, review UI, and LLM judge design.

### Changed

- Bump Python package, runtime schema fixture, and local UI package versions from `0.1.3` to `0.2.0`.
- Extend canonical config with default-off `trace` and `judge` sections; credentials remain environment-only via `MICRO_EVAL_SECRET_*` declarations.
- Update README, Chinese README, development guide, PRD, and example config to describe the current Phase 2 codebase.
- Decision and report surfaces now display cost source / unavailable-cost state instead of implying cost data always exists.
- Optional Langfuse and DeepEval integrations are loaded through optional extras/importlib and are not required for local MVP runs.

### Fixed

- Keep deterministic validator pass/fail authoritative when supplemental judge evaluations disagree.
- Degrade optional trace provider failures through fallback warnings instead of failing a run.
- Preserve old run compatibility by reading `decision.json` first and falling back to legacy embedded `run.json.decision`.
- Keep trace/judge output within existing redaction, manifest, artifact, and workspace boundaries.

### Verification

- `uv run python -m compileall src/micro_eval tests`
- `uv run pytest -q` — latest implementation gate: 89 passed
- `cd ui && npm run lint && npm run build`
- `uv run python examples/run-example.py`
- `git diff --check`
- Security greps for `create_subprocess_shell` and `shell=True` across `src`, `tests`, `ui`, and `examples`
- Optional SDK boundary grep for direct `import deepeval` / `import langfuse` in trusted implementation paths

### Known Gaps

- Langfuse cost extraction remains best-effort and depends on the optional SDK/runtime payload shape.
- Token-count × price-table cost estimation and calibrated larger-sample statistics are not implemented in 0.2.0.
- ATIF import/export and hosted collaboration remain out of scope for this local-first release.
- The UI still uses lint/build validation; no Vitest suite is configured yet.

## 0.1.3 - 2026-06-03

### Added

- Promote the MVP to the canonical `tasks × configurations × repetitions` execution model with `RunPlan`, `RunCell`, canonical Pydantic contracts, and matching TypeScript/zod contracts.
- Add `micro-eval init`, `validate`, `run`, `list`, `report`, and `ui` as the local Golden Path for creating a project, validating configuration, running a matrix, reviewing evidence, and opening the local UI.
- Add canonical run storage at `.micro-eval/runs/{run_id}/` with `run.json`, `manifest.json`, per-cell `result.json`, text artifacts, and append-only `evaluation.json` records.
- Add `SameStartSnapshot`, `CellSnapshot`, `SnapshotGateResult`, and `ReplayCanonical` so every decision can be traced back to comparable starting conditions.
- Add managed workspaces for `blank`, `files`, and `git_repo` tasks; `git_repo` tasks execute in isolated git worktrees.
- Add deterministic validators for `exit_code`, `contains`, `file_exists`, and argv-only `command` expectations.
- Add persistent human evaluation through the Next.js API and UI; human scoring is appended to disk and recomputes the run decision instead of trusting browser storage.
- Add guarded `DecisionReport` / Basic Honest Stats so degraded comparability produces `not_comparable` or `inconclusive` instead of overstating a winner.
- Add a manifest-backed artifact viewer in the local UI and static text/json/html reports with caveats, stats, matrix rows, and artifact references.
- Add starter task templates under `tasks/templates/` and a deterministic dogfood suite covering the MVP Golden Path.
- Add a final quality gate checklist for the 0.1.3 release.

### Changed

- Bump Python package and local UI package versions from `0.1.2` to `0.1.3`.
- Update `README.md` and `docs/DEVELOPMENT.md` to describe the completed canonical MVP workflow instead of the legacy baseline/candidate-only flow.
- New projects should use canonical `configurations[]`; legacy `baseline` / `candidate` configuration still loads through an explicit migration bridge with warnings.
- Agent and validation commands are canonical argv lists. Shell-string execution is not part of the trusted execution path.
- `output_dir` is constrained to a project-relative path and run artifacts are resolved through the project/run boundary.
- Text artifacts, evidence summaries, and human-evaluation comments are redacted before persistence when they contain `MICRO_EVAL_SECRET_*` values.
- HTML reports now render through Jinja with autoescaping enabled.
- The Next.js UI now reads canonical run/cell/artifact/evaluation data from local API routes and exposes artifact content only by manifest `artifact_id`.

### Fixed

- Complete the 0.1.2 known gaps for canonical run layout, configuration matrix planning, same-start snapshots, evidence/artifact references, and persisted human evaluation.
- Avoid run ID collisions with timestamp-plus-random run identifiers.
- Fix `output_mode=file` false positives by requiring a real, regular output file and classifying missing output correctly.
- Prevent reserved artifact paths (`stdout.txt`, `stderr.txt`, `output.txt`) from following agent-created symlinks or hardlinks.
- Skip or mark symlinked, linked, oversized, and binary artifacts instead of exposing unsafe raw content.
- Align Python and TypeScript decision recomputation semantics for persisted human evaluations.
- Include workspace fingerprints, workspace maps, and guardrail digests in replay/same-start evidence so replay comparability covers the real run boundary.
- Align `VERSION`, Python `__version__`, UI package lock metadata, and `ReplayCanonical.tool_version` on `0.1.3` so release artifacts and run evidence no longer report stale versions.

### Verification

- `uv run python -m compileall src/micro_eval tests`
- `uv run pytest -q` — latest release gate: 67 passed
- `cd ui && npm run lint && npm run build`
- `uv build`
- Wheel smoke test with a Python `>=3.11` virtual environment
- `git diff --check`
- Security greps for `create_subprocess_shell`, `shell=True`, `localStorage`, and `sessionStorage`
- Independent code review: APPROVE
- Independent architecture review: CLEAR
- UltraQA adversarial MVP smoke: PASS

### Known Gaps

- Langfuse observability remains optional/future work; MVP runs degrade cleanly without it.
- DeepEval is reserved for scoring-library integration; the MVP does not use the DeepEval test runner.
- OpenHands sandbox integration, multi-team collaboration, RBAC/SSO, large-scale task libraries, and recommendation engines are intentionally out of MVP scope.

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
