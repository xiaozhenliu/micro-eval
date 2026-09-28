---
title: Development Guide
language: en
authoritative: true
doc_type: guide
status: active
created_at: 2026-09-27T15:56+08:00
updated_at: 2026-09-27T15:56+08:00
owner: micro-eval maintainers
---

# Development Guide

This is the engineering entry point. Authoritative engineering guidelines live in `docs/engineering/`. A Chinese companion translation (`DEVELOPMENT.zh-CN.md`) exists for human reading; this English file is authoritative, and agents must follow it rather than any translation.

**Internal design docs** (developer reference):
- `docs/superpowers/specs/2026-06-02-unicorn-design.md` — long-term architecture
- `docs/superpowers/specs/2026-06-02-unicorn-design.md` §9–§10 — current implementation scope (the historical MVP profile is archived at `docs/_archive/2026-06-02-mvp-profile.md`)
- `docs/superpowers/specs/2026-06-02-test-architecture.md` — test architecture

**User documentation site** (`site/`):
- Organization: Get Started → Using micro-eval → Advanced → Reference
- Design system page: `site/guide/design-system.md` (decision loop, 3 tensions, 7 core objects)
- User docs contain no implementation details; internal docs do not restate user concepts. The two doc sets serve different audiences.

The Work Register is the Linear project `micro-eval` (team `GRO`); the contract lives in `docs/agents/issue-tracker.md`, and `uv run python scripts/check-work-governance.py` runs the offline governance check over archives and projection policy. Release evidence lives in `docs/releases/`. The full release process is `docs/engineering/release-process.md`, with companion scripts under `scripts/release/`.

## Development principles

- Daily development happens on the `dev` branch; do not develop directly on `main`.
- No TDD: understand the spec and the user path first, design module boundaries, implement a runnable vertical slice, then add acceptance/regression/contract tests.
- Python code comments are in English; user communication is in Simplified Chinese.
- subprocess calls are argv-only; shell interpolation is forbidden.
- Changes touching env/stdout/stderr/artifact/workspace must be checked against `docs/engineering/security-guidelines.md`.
- Do not bypass the canonical schemas; the Python Pydantic and TypeScript zod contracts must stay aligned.

## Environment setup

Python `>=3.11` is required.

```bash
uv sync --all-extras
cd ui && npm install
```

This project manages the local Python environment with `uv`. `uv sync --all-extras` creates or updates `.venv/` at the project root; prefer `uv run ...` for project commands and do not rely on the current shell's `python` or a globally installed `micro-eval`:

```bash
uv run python --version
uv run micro-eval --help
uv run pytest -q
```

The Zed project settings disable automatic `.venv` activation in the integrated terminal, so the terminal keeps the user's default zsh prompt; the runtime environment is still selected by `uv run` from `.venv`.

Common local commands:

```bash
uv run micro-eval --help
uv run micro-eval init --force
uv run micro-eval validate
uv run micro-eval run --dry-run --format json
```

## Example smoke

The examples in a source checkout provide one cross-platform entry point for exercising the basic CLI, workspace, run store, and report chain:

```bash
uv run python examples/run-example.py
```

The script runs a deterministic mock matrix with `examples/agent-codefix-showdown/` as the eval project and produces:

- run store: `examples/agent-codefix-showdown/.micro-eval/runs/`
- cell workspaces: `examples/agent-codefix-showdown/.micro-eval/workspaces/{run_id}/{cell_id}/`
- static report: `examples/agent-codefix-showdown/report.html`

`report.html` and `.micro-eval/` are runtime artifacts and are git-ignored. By default cell workspaces are cleaned up after the cell finishes; the run record keeps the path evidence in `cell_snapshot.workspace_path`.

A real agent matrix still requires explicit opt-in:

```bash
uv run python examples/run-example.py --real
```

## Local verification

Run at least the following for functional or release-related changes:

```bash
uv run python -m compileall src/micro_eval tests
uv run pytest -q
cd ui && npm run lint && npm run build
uv build
git diff --check
grep -R "create_subprocess_shell" src tests ui || true
grep -R "shell=True" src tests ui || true
grep -R "localStorage" ui/src || true
grep -R "sessionStorage" ui/src || true
```

For changes touching examples, workspaces, subprocess, artifacts, or security boundaries, also sample at least:

```bash
uv run python examples/run-example.py
grep -RInE 'create_subprocess_shell|shell=True' src tests ui examples || true
```

Documentation-only changes may run only `git diff --check`, but when the docs update commands, schemas, workspace paths, or release claims, sample-run the relevant commands to confirm.

## Main modules

```text
src/micro_eval/
├── cli/                 # init / validate / run / list / report / apply-evaluation / ui / serve / worker / workspace / template / queue / build-plan
├── config/              # loader bridge + RunPlan builder
├── engine/              # AgentAdapter, ExecutionKernel, WorkspaceManager, providers/ (Seatbelt/Bubblewrap/E2B/Modal), agent_bridge.py (JSONL multi-turn bridge)
├── evaluation/          # deterministic validator + human evaluation + optional LLM judge helper
├── decision/            # guarded DecisionReport + pass@k/pass^k aggregation
├── trace/               # optional TraceProvider adapters (process fallback, Langfuse optional)
├── models/              # canonical Pydantic contracts
├── server/              # Team Server layer: workspace, template registry, queue, worker (v0.4)
└── store/               # RunStore / ArtifactStore

ui/src/
├── app/                 # pages and API routes (project-scoped + workspace-scoped)
│   └── api/workspaces/  # server-mode workspace/run/queue/template API routes
├── components/          # RunList, MatrixHeatmap, CellDetail, WorkspaceCard, QueueDashboard, etc.
└── lib/                 # zod schema, fs data access, server-mode utilities, workspace API
```

## Canonical data flow

1. `load_config()` reads the canonical `configurations[]`; legacy `baseline` / `candidate` is converted only through the migration bridge.
2. `build_run_plan()` expands `tasks × configurations × repetitions` and produces the `SameStartSnapshot` and `ReplayCanonical`.
3. The `ExecutionKernel` allocates a workspace for each cell under the current eval project's `.micro-eval/workspaces/{run_id}/{cell_id}/`, invokes the `AgentAdapter`, and writes stdout/stderr/output artifacts.
4. `validate_cell()` produces the validator `EvaluationResult` and validation evidence; with `judge.enabled=true` a supplemental judge evaluation may be appended but must never override the deterministic cell pass/fail.
   - When `judge.provider == "deepeval_conversational"`, the kernel takes the conversational branch (`_execute_cell_conversational`): `SubprocessBridge` keeps the agent process alive and drives it turn by turn over JSONL; the `conversational_judge` module scores in two phases (`simulate_conversation()` → `score_conversation()`); results go to the `conversation.json` artifact and `conversational_judge`-typed evidence, and the CellResult points to that artifact via `conversation_ref`. Deterministic pass/fail semantics are not overridden by this branch.
5. `TraceProvider` collects `TraceRef` when `trace.enabled=true`; the `process` fallback needs no SDK, and `langfuse` is wired through an optional extra/importlib.
6. `RunStore` writes `.micro-eval/runs/{run_id}/run.json` and the sibling `decision.json`; `ArtifactStore` writes `manifest.json` (covering artifacts/evidence/traces).
7. `build_decision()` produces a guarded `DecisionReport` from pass@k/pass^k, latency, cost source, and caveats; a snapshot mismatch degrades the decision to `not_comparable`.
8. The UI/API reads canonical JSON through zod; human evaluation POSTs append to the cell `evaluation.json` and recompute `decision.json` / `run.json.decision`.

## Workspace boundary

`WorkspaceManager` is the single entry point for workspace paths and lifecycle. During development, never create an agent cwd on your own in adapters, validators, reports, or the UI.

The current MVP supports three task workspace types:

| `workspace.type` | Runtime behavior |
| --- | --- |
| `blank` | Creates an empty directory under the current eval project's `.micro-eval/workspaces/{run_id}/{cell_id}/`. |
| `files` | Copies the declared files/directories into `.micro-eval/workspaces/{run_id}/{cell_id}/`. |
| `git_repo` | Resolves `ref` to a commit and creates a detached git worktree at `.micro-eval/workspaces/{run_id}/{cell_id}/`. |

Security boundaries:

- The agent cwd must live inside the current eval project's `.micro-eval/workspaces/{run_id}/{cell_id}/`.
- Never place the agent cwd in a system temp directory or outside the project without explicit user configuration.
- Both setup commands and agent commands must be argv-only.
- A failed cell workspace cleanup must surface in snapshot/evidence instead of being swallowed silently.
- Raw workspace paths are path evidence only in snapshot/evidence; UI/API display of artifact content must still go through the manifest/ref boundary.

## CLI smoke

```bash
tmpdir=$(mktemp -d)
cd "$tmpdir"
uv run --project /path/to/micro-eval micro-eval init --force
uv run --project /path/to/micro-eval micro-eval validate --format json
uv run --project /path/to/micro-eval micro-eval run --dry-run --format json
uv run --project /path/to/micro-eval micro-eval run --max-concurrency 2 --format json
uv run --project /path/to/micro-eval micro-eval list --format json
uv run --project /path/to/micro-eval micro-eval report --format text
uv run --project /path/to/micro-eval micro-eval report --format html --output report.html
```

## Contract fixture discipline

- Python canonical models are the source for persisted run artifacts.
- UI zod schemas must parse real run artifacts, not hand-written approximations.
- Keep `ui/src/lib/fixtures/canonical-run-p0.json` and `tests/unit/test_contract_fixture.py` aligned when schema changes.
- When changing `RunRecord`, `CellResult`, `ArtifactRef`, `EvidenceItem`, `EvaluationResult`, or `DecisionReport`, update both Python and TS contract coverage in the same vertical slice.

## Security review checklist

- **shell interpolation**: canonical agent commands and validation commands are argv lists; no `shell=True` or `create_subprocess_shell` in trusted execution paths.
- **secrets redaction**: only declared `MICRO_EVAL_SECRET_*` values are injected, and all non-empty host `MICRO_EVAL_SECRET_*` values participate in redaction before text artifact/evidence/UI persistence.
- **workspace boundary**: the agent cwd is the assigned blank/files/git worktree workspace under the current eval project's `.micro-eval/workspaces/`; setup env is allowlisted and does not inherit secrets.
- **output_dir boundary**: `output_dir` must be project-relative and must not contain `..`.
- **artifact safety**: reserved stdout/stderr/output paths are written atomically; symlink, hardlink, non-regular, oversized, and binary artifacts are skipped or represented with warnings/placeholders.
- **raw artifact access**: Decision/UI consume refs and summaries; raw text content is available only through explicit manifest `artifact_id` lookup plus run-dir `realpath` boundary validation.
- **snapshot mismatch**: Decision must stay guarded and never claim strong improvement/regression when comparability is degraded.
- **trace/judge safety**: Trace and the LLM judge are off by default; external SDKs are wired only through optional extras/importlib, credentials come only from `MICRO_EVAL_SECRET_*` environment variables, and are never written into config/artifact/release docs.

For workspace-related changes, additionally check:

- `tests/e2e/test_p0b_reproducibility_flow.py::test_files_workspace_stays_under_project_workspaces_dir`
- `tests/e2e/test_p0b_reproducibility_flow.py::test_git_repo_workspace_runs_in_isolated_worktree_with_snapshot`
- whether the example smoke's latest `cell_snapshot.workspace_path` sits under the current example project's `.micro-eval/workspaces/`.

## Release readiness checklist

Before claiming a release-ready MVP:

1. Run the verification commands above.
2. Run a deterministic CLI smoke in a temporary project.
3. Build the package with `uv build`.
4. Install the wheel in a Python `>=3.11` virtual environment and run a CLI smoke.
5. Run or review UltraQA adversarial scenarios for normal path, malformed argv, misleading exit code, timeout, secret leakage, artifact traversal, and binary artifact handling.
6. Get independent code-review and architecture review evidence when the release risk warrants it.
7. Record final evidence in `docs/releases/`, generate the dependency inventory with `scripts/release/generate-dependency-inventory.py --version <version>`, and follow `docs/engineering/release-process.md` for version, commit, tag, and dev→main projection gates.
