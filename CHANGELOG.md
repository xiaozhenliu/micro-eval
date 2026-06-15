# Changelog

All notable changes to `micro-eval` are documented here.

## 0.3.4 - 2026-06-15

### Changed

- The UI evaluate endpoint now delegates to Python `build_decision` via subprocess instead of maintaining a separate TypeScript reimplementation (#1). The `micro-eval apply-evaluation` CLI command accepts a JSON payload on stdin, constructs the human evaluation via `build_human_evaluation`, appends it through `RunStore.append_evaluation`, and returns the recomputed decision on stdout. This makes Python the single source of truth for the decision algorithm.

### Removed

- Delete `ui/src/lib/evaluation.ts` (226 lines): `recomputeDecision`, `appendEvaluationToRun`, `buildHumanEvaluation`, `appendEvaluationFile`, and all helper functions (`aggregateCost`, `passAtK`, `passHatK`, `combination`, `dedupe`, `median`, `redactSecrets`, `safePathSegment`). The decision algorithm, evaluation construction, and file persistence are now handled exclusively by the Python engine.
- Delete `ui/src/lib/__tests__/decision-equivalence.test.ts` and `ui/src/lib/__tests__/evaluation.test.ts` — the cross-language equivalence contract is no longer needed since only one implementation exists. The Python golden test (`test_golden.py::test_decision_equivalence_golden_matches_python_algorithm`) continues to guard `build_decision` against regression.

### Added

- New CLI command `micro-eval apply-evaluation --run-id <id> --cell-id <id>` that reads evaluation input from stdin JSON and outputs `{evaluation, evidence, decision}` to stdout. Supports `MICRO_EVAL_UV_PATH` environment variable for custom `uv` binary path.

## 0.3.3 - 2026-06-15

### Added

- **Project documentation website** built with VitePress, deployed to GitHub Pages at `https://xiaozhenliu.github.io/micro-eval/`.
  - 10 English guide pages covering introduction, getting started, core concepts, configuration, tasks, execution, evaluation, decision/caveats, workspace isolation, trend analysis, and security model.
  - 6 English reference pages: CLI commands, eval.yaml schema, task.yaml schema, data model, API routes, and Web UI.
  - 4 English example pages: overview with capability coverage matrix, agent codefix showdown, multi-task matrix, and git workspace isolation.
  - Complete Simplified Chinese translation (21 pages) with native i18n routing (`/zh/` prefix).
  - Custom theme with brand colors (#6f42c1 purple), dark mode support, and Mermaid diagram rendering.
  - GitHub Actions workflow for automatic deployment on push to `main` (path-scoped to `site/**`).
  - Built-in local search via VitePress MiniSearch.
- Documentation site link added to both README.md and README.zh-CN.md.

### Fixed

- **Python 3.12 CI deadlock**: the `test_cancelled_error_propagates_not_isolated` test hung indefinitely on Python 3.12 due to `asyncio.run()` cleanup behavior change — 3.12's `_cancel_all_tasks()` gathers orphaned subprocess tasks stuck in `selector.select()` (a C-level blocking call immune to `task.cancel()`), causing an infinite deadlock. Fixed by using a dedicated event loop with `loop.close()` which tears down the selector without waiting.
- **CI shell-injection grep gate**: the grep gate falsely matched `create_subprocess_shell` string literals inside `test_execution_contract.py` (the test that asserts production code does NOT contain those patterns). Fixed with `--exclude='test_execution_contract.py'`.

### Changed

- Version bump to 0.3.3 (Python `__init__.py`, UI `package.json`, VERSION, READMEs).
- Add `pytest-timeout>=2.0` to dev dependencies and `--timeout=60` / `timeout-minutes: 10` to CI as defense-in-depth against future test hangs.

## 0.3.2 - 2026-06-15

### Added

- **Test coverage expansion**: overall line coverage rises from ~78% (224 tests) to 91% (455 tests), closing gaps across CLI, engine, evaluation, store, and trace layers.
  - New test files targeting previously uncovered paths in `cli/init.py`, `cli/list.py`, `cli/run.py`, `cli/validate.py`, `cli/report.py`, `engine/adapter.py`, `engine/kernel.py`, `engine/providers/git_worktree.py`, `engine/providers/remote.py`, `evaluation/llm_judge.py`, `store/artifact_store.py`, `store/run_store.py`, `store/sqlite_store.py`, `trace/langfuse_provider.py`, `decision/trend.py`, and model validators.
  - Key coverage improvements: `cli/init.py` 0%→100%, `cli/list.py` 0%→97%, `cli/main.py` 0%→58%, `engine/providers/os_policy.py` →100%, `decision/trend.py` 71%→100%, `models/configuration.py` 85%→100%, `models/run.py` →100%, `engine/workspace.py` →99%.
  - Coverage spec: `docs/superpowers/specs/2026-06-15-test-coverage-plan.md`.

### Changed

- Version bump to 0.3.2 (Python `__init__.py`, UI `package.json`).

## 0.3.1 - 2026-06-15

### Added

- **Example coverage expansion**: two new examples demonstrate the remaining ~50% of project capabilities.
  - `examples/multi-task-matrix/` — 2 configs × 3 tasks × 2 reps (12 cells) exercising all four expectation types (`exit_code`, `contains`, `file_exists`, `command`), workspace `setup` commands, and a deliberately partial-failing candidate that produces an `inconclusive` decision.
  - `examples/git-workspace-isolation/` — `git_repo` workspace with per-cell git worktree isolation, OS policy sandbox configuration (Seatbelt/Bubblewrap), fixture digest + toolchain fingerprint in `SameStartSnapshot`, and two-run trend analysis with a drift breakpoint.
- `examples/run-example.py` now supports `--example <name>` to run individual examples or `--example all` to run all sequentially; `--skip-run` and `--max-concurrency` are forwarded to delegated examples.
- `examples/README.md` adds a capability coverage matrix across all three examples and an "Advanced: Optional External Integrations" section with YAML snippets for LLM Judge, Langfuse, secrets channel, and E2B/Modal remote VM.
- Overall example capability coverage rises from ~50% to ~85%.

### Changed

- Version bump to 0.3.1 (Python, UI, VERSION file, READMEs).

## 0.3.0 - 2026-06-14

### Added

- **P3-a: WorkspaceProvider abstraction** — introduce `WorkspaceProvider` Protocol, `ProviderRegistry`, and `IsolationLevel`/`TrustLevel`/`NetworkPolicy` enums (spec §3.4.4). Refactor the existing worktree logic into `GitWorktreeProvider` (Level 0, logical isolation). `WorkspaceManager` becomes a registry facade; all existing behavior is preserved (zero behavior change).
- **P3-b: OS policy sandbox** — add `SeatbeltProvider` (macOS `sandbox-exec`) and `BubblewrapProvider` (Linux `bwrap`) for Level 1 semi-trusted isolation. Filesystem writes restricted to workspace directory; network policy configurable (full/allowlist/none). Platform unavailability degrades gracefully to Level 0 with a caveat; higher levels (container/vm) never degrade locally.
- **P3-c: Remote providers** — add `E2BProvider` (VM, Level 4 adversarial) and `ModalProvider` (container, Level 3 untrusted) for remote sandbox execution. Credentials required via `MICRO_EVAL_SECRET_*` env vars; missing credentials → fail hard with clear error (no silent local degradation). Artifact/stdout/stderr handling follows existing redaction and cap boundaries.
- **P3-d: Complex workspace types** — add `FixtureSource` (per-source sha256 digest) and `ToolchainSpec` (runtime/lockfile declaration) to `WorkspaceSpec`. Fixture digests and toolchain fingerprint flow into `SameStartSnapshot` as comparability dimensions; mismatches produce caveats through the existing P0-b gate.
- **P3-e: Trend analysis + SQLite** — add `SqliteStore` as a derived index over JSON run data (JSON remains source of truth). `run_store.finalize_run` auto-indexes to SQLite; existing JSON runs importable via `import_json_runs`. Add `compute_trend`/`compute_all_trends` with drift-aware breakpoints (reusing #2 configuration drift logic). Add Next.js `/api/trends` route backed by `better-sqlite3`.
- New fields on `SameStartSnapshot`: `sandbox_policy`, `network_policy`, `toolchain_fingerprint`, `fixture_digests` — all with backward-compatible defaults.
- 52 new tests: provider protocol (16), OS policy provider (15), remote provider (14), SQLite/trends (7).
- Zod schema and contract golden fixtures updated for all new fields.

### Security

- `exec_command` enforces argv-only execution across all providers (negative tests for empty argv and empty-string elements).
- Remote providers use `MICRO_EVAL_SECRET_*` naming convention for automatic redaction compatibility.
- Seatbelt profile verified: workspace-external writes are denied (negative test on macOS).
- Container/VM isolation levels fail hard when no provider is available — untrusted code never silently falls back to local execution.
- Shell interpolation zero-match gate: `grep -RInE 'create_subprocess_shell|shell=True' src tests ui examples` — clean.

### Changed

- `WorkspaceManager` now uses provider registry internally; public API unchanged.
- `build_same_start_snapshot` collects isolation levels, network policies, fixture digests, and toolchain fingerprints as comparability dimensions; mixed isolation/network in a single run produces a caveat.
- `kernel._execute_cell` flows workspace-level caveats (e.g., os_policy degradation) into the snapshot gate result.

## 0.2.10 - 2026-06-14

### Added

- Record per-run execution order: `RunRecord.execution_order` always captures the order cells were dispatched (order-effect provenance), and an opt-in `Guardrails.randomize_execution_order` shuffles the dispatch order with a recorded `execution_seed` so a randomized run stays reproducible. Default off keeps deterministic plan order. (P3, from the 2026-05-31 engineering review.)

## 0.2.9 - 2026-06-14

### Changed

- Default `max_concurrency` is now 4 (was 2) to match the spec; `Guardrails`, the `micro-eval init` template, and the run fallback all align (#9).
- The default artifact size cap is now a distinct 50MB (output cap stays 10MB), in both `Guardrails` and `ArtifactStore`, so large artifacts are not capped at the smaller output limit (#9).

### Added

- Persist the per-cell truncation flags (`stdout_truncated`/`stderr_truncated`/`output_truncated`) on `CellResult` (Python + zod) so a truncated output is no longer silently dropped before the report/UI (#9).

### Notes

- Remaining #9 items are deliberate keeps: trace_id stays `trace_id == cell_id` because cost aggregation matches on it (the spec format would break matching — spec to be updated, not code); the error-classification rename and redactor-naming/spec-field alignment are cosmetic/spec-only and deferred.

## 0.2.8 - 2026-06-14

### Removed

- Retire the unreachable legacy execution/scoring stack (#3, #4): `engine/runner.py` (the v0.1 `AgentRunner`), `engine/scorer.py` (`Scorer`), `models/schema.py` (legacy `AgentConfig`/`Run`/`Task`/…), the `legacy_agent_config` converter, and the `ProjectConfigV2.baseline`/`candidate`/`parallel` legacy view properties. These were reachable only from tests; agent execution runs through `AgentAdapter`/`ExecutionKernel` and decisions through `build_decision`.

### Changed

- The report CLI reads legacy run.json directly through `RunRecord` (which absorbs the v0.1.x shape) instead of a separate legacy `Run` model (#4), removing the last production dependency on `models/schema.py`. The execution contract test now asserts `AgentAdapter` is the *only* async agent spawner in the engine.

## 0.2.7 - 2026-06-14

### Added

- Emit a cross-run comparability caveat when a configuration id is reused but its content changed since the most recent prior run with that id (#2). The decision now warns that the same matrix "column" no longer means the same thing instead of comparing silently. Detection lives in the kernel (which has run-history access) and is surfaced through the same-start snapshot caveats.
- Add rendering contract tests for the report CLI (text + HTML branches), covering the pass@k column, caveat rendering, and HTML autoescaping; `cli/report.py` line coverage rises from 32% to 69%.

## 0.2.6 - 2026-06-14

### Changed

- The deterministic validator now records `rubric_hash` on its `EvaluationResult`, like the LLM judge already did (#8). Both evaluator paths share a single `rubric_digest` helper, so a given rubric yields one identical hash regardless of which evaluator recorded the result, keeping evaluation provenance comparable across evaluator types.

### Added

- Add execution-layer contract tests (#5): the run kernel must delegate agent process spawning to `AgentAdapter` (no direct subprocess spawning), and a timed-out agent must escalate SIGTERM → SIGKILL only after the grace window. These cover the two remaining #5 contracts; the shell-injection gate already runs in CI.

## 0.2.5 - 2026-06-14

### Fixed

- Unify binary-content detection across the adapter and the artifact store (#12). The artifact store previously inspected only the first 1024 bytes, so a binary file whose first NUL byte appeared later was mislabelled `text/plain` and marked `redacted=true`. Both call sites now use a shared `looks_binary` helper that scans the whole buffer, matching the adapter.

### Changed

- The zod `EvaluationResult` schema now enforces, like the Python model, that a `pass_fail` verdict must carry at least one `evidence_refs` entry (#6). Previously the UI silently accepted an evidence-less pass/fail evaluation that the Python side rejects.

## 0.2.4 - 2026-06-14

### Fixed

- `recomputeDecision` (UI) now aggregates per-configuration trace cost from `run.traces` instead of hard-coding `total_cost` to `unavailable` (#1). Previously, appending a human evaluation recomputed the decision and silently wiped any cost that the Python `build_decision` had produced.

### Added

- Add a cross-language decision-algorithm equivalence contract (#1): `scripts/generate-golden.py` pins a canonical input run together with the decision the Python `build_decision` produces for it (`tests/contract/golden/decision-equivalence.json`). A pytest check asserts the fixture stays in sync with `build_decision`, and a vitest check feeds the same input to `recomputeDecision` and asserts an identical (time-stripped, tolerance-compared) decision — so algorithmic drift between the Python and UI implementations now fails CI, not just schema-shape drift.

## 0.2.3 - 2026-06-14

### Fixed

- Validate `file_exists` and `command` expectations against the agent's actual workspace directory instead of the artifact output directory (#13). Expectations may still opt into the artifact directory with the `{output_dir}` placeholder.
- Isolate per-cell failures in the run kernel: a cell that raises an unexpected exception now degrades to an isolated failure result (with redacted stderr) instead of aborting the whole run (#14). `CancelledError` still propagates so cancellation is not swallowed.

### Security

- Constrain `git_repo` and `files` workspace source paths to the project root, consistent with the existing RunStore/ArtifactStore containment guards (#10). A new shared `_assert_within_root` guard covers all three workspace entry points (`_resolve_source_path`, `_copy_files`, `build_same_start_snapshot`); out-of-root sources are rejected during preparation and recorded as a task-tagged caveat during same-start snapshotting.

## 0.2.2 - 2026-06-12

### Added

- Add a GitHub Actions CI pipeline (no secrets, read-only token): pytest with a 75% coverage gate on Python 3.11/3.12, compileall plus a shell-injection grep gate, golden fixture sync check, UI lint/vitest/build, and the example smoke run.
- Add a contract golden mechanism: `scripts/generate-golden.py` deterministically generates all cross-language contract fixtures under `tests/contract/golden/` from Pydantic models; pytest validates round-trip/idempotency/no-secrets and vitest consumes the same files with strict stripped-field detection, so Pydantic↔zod drift in either direction fails CI.

### Changed

- Hand-maintained UI contract fixtures and `tests/fixtures/legacy/` are replaced by generated golden files (the P0 canonical fixture stays at its original path for release preflight compatibility).

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
