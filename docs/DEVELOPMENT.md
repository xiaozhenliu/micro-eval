# 开发指南

本文是当前 0.1.3 MVP 实现的工程入口。正式工程规范仍以 `docs/engineering/` 为准；长期架构/范围权威来源仍是：

- `docs/superpowers/specs/2026-06-02-unicorn-design.md`
- `docs/superpowers/specs/2026-06-02-mvp-profile.md`
- `docs/superpowers/specs/2026-06-02-test-architecture.md`

MVP release evidence 见 `docs/releases/2026-06-02-mvp-release-evidence.md`；完整 release 流程见 `docs/engineering/release-process.md`。

## 开发原则

- 日常开发在 `dev` 分支；不要直接在 `main` 开发。
- 禁止 TDD：先理解规格与用户路径，再设计模块边界，实现可运行垂直切片，最后补验收/回归/契约测试。
- Python 代码注释使用英文；用户沟通使用简体中文。
- subprocess 必须 argv-only，禁止 shell interpolation。
- 涉及 env/stdout/stderr/artifact/workspace 的改动必须按 `docs/engineering/security-guidelines.md` 检查。
- 不要绕过 canonical schema；Python Pydantic 与 TypeScript zod contract 必须保持一致。

## 环境准备

Python 要求 `>=3.11`。

```bash
uv sync --all-extras
cd ui && npm install
```

常用本地命令：

```bash
uv run micro-eval --help
uv run micro-eval init --force
uv run micro-eval validate
uv run micro-eval run --dry-run --format json
```

## 本地验证

功能或 release 相关改动至少运行：

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

纯文档改动可只运行 `git diff --check`，但如果文档更新了命令、schema 或 release claims，应抽样运行相关命令确认。

## 主要模块

```text
src/micro_eval/
├── cli/                 # init / validate / run / list / report / ui
├── config/              # loader bridge + RunPlan builder
├── engine/              # AgentAdapter, ExecutionKernel, WorkspaceManager
├── evaluation/          # deterministic validator + human evaluation helper
├── decision/            # guarded DecisionReport / Basic Honest Stats
├── models/              # canonical Pydantic contracts
└── store/               # RunStore / ArtifactStore

ui/src/
├── app/                 # pages and API routes
├── components/          # RunList, ResultMatrix, CellDetail, ArtifactViewer, EvaluationPanel
└── lib/                 # zod schema, fs data access, evaluation append helpers, contract fixture
```

## Canonical 数据流

1. `load_config()` 读取 canonical `configurations[]`；legacy `baseline` / `candidate` 只通过 migration bridge 转换。
2. `build_run_plan()` 展开 `tasks × configurations × repetitions`，生成 `SameStartSnapshot` 与 `ReplayCanonical`。
3. `ExecutionKernel` 为每个 cell 分配 workspace，调用 `AgentAdapter`，写入 stdout/stderr/output artifacts。
4. `validate_cell()` 生成 validator `EvaluationResult` 与 validation evidence。
5. `RunStore` 写入 `.micro-eval/runs/{run_id}/run.json`，`ArtifactStore` 写入 `manifest.json`。
6. `build_decision()` 生成 guarded `DecisionReport`；snapshot mismatch 降级为 `not_comparable`。
7. UI/API 通过 zod 读取 canonical JSON；human evaluation POST append 到 cell `evaluation.json` 并重算 `run.json.decision`。

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

- **shell interpolation**：canonical agent commands and validation commands are argv lists; no `shell=True` or `create_subprocess_shell` in trusted execution paths.
- **secrets redaction**：only declared `MICRO_EVAL_SECRET_*` values are injected, and all non-empty host `MICRO_EVAL_SECRET_*` values participate in redaction before text artifact/evidence/UI persistence.
- **workspace boundary**：agent cwd is the assigned blank/files/git worktree workspace; setup env is allowlisted and does not inherit secrets.
- **output_dir boundary**：`output_dir` must be project-relative and must not contain `..`.
- **artifact safety**：reserved stdout/stderr/output paths are written atomically; symlink, hardlink, non-regular, oversized, and binary artifacts are skipped or represented with warnings/placeholders.
- **raw artifact access**：Decision/UI consume refs and summaries; raw text content is available only through explicit manifest `artifact_id` lookup plus run-dir `realpath` boundary validation.
- **snapshot mismatch**：Decision must stay guarded and never claim strong improvement/regression when comparability is degraded.

## Release readiness checklist

Before claiming a release-ready MVP:

1. Run the verification commands above.
2. Run a deterministic CLI smoke in a temporary project.
3. Build the package with `uv build`.
4. Install the wheel in a Python `>=3.11` virtual environment and run a CLI smoke.
5. Run or review UltraQA adversarial scenarios for normal path, malformed argv, misleading exit code, timeout, secret leakage, artifact traversal, and binary artifact handling.
6. Get independent code-review and architecture review evidence.
7. Record final evidence in `docs/releases/` and follow `docs/engineering/release-process.md` for version, dependency inventory, commit, tag, and dev→main projection gates.
