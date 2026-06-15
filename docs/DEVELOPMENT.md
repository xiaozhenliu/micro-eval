# 开发指南

本文是工程入口。正式工程规范以 `docs/engineering/` 为准。

**内部设计文档**（开发者参考）：
- `docs/superpowers/specs/2026-06-02-unicorn-design.md` — 长期架构
- `docs/superpowers/specs/2026-06-02-mvp-profile.md` — MVP 范围
- `docs/superpowers/specs/2026-06-02-test-architecture.md` — 测试架构

**用户文档站点**（`site/`）：
- 组织方式：Get Started → Using micro-eval → Advanced → Reference
- 设计体系页：`site/guide/design-system.md`（决策闭环、3 张力、7 核心对象）
- 用户文档不包含实现细节；内部文档不重述用户概念。两套文档服务不同受众。

Release evidence 见 `docs/releases/`。完整 release 流程见 `.codex/skills/micro-eval-release/SKILL.md`。

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

## Example smoke

源码 checkout 中的 example 提供一条跨平台入口，适合验证 CLI、workspace、run store 与 report 基本链路：

```bash
uv run python examples/run-example.py
```

该脚本从 `examples/agent-codefix-showdown/` 作为 eval project 运行 deterministic mock matrix，并生成：

- run store：`examples/agent-codefix-showdown/.micro-eval/runs/`
- cell workspace：`examples/agent-codefix-showdown/.micro-eval/workspaces/{run_id}/{cell_id}/`
- static report：`examples/agent-codefix-showdown/report.html`

`report.html` 与 `.micro-eval/` 属于运行时产物，已被 git ignore。默认情况下 cell workspace 会在 cell 结束后 cleanup；run 记录中的 `cell_snapshot.workspace_path` 保留路径证据。

真实 agent matrix 仍需显式 opt-in：

```bash
uv run python examples/run-example.py --real
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

涉及 examples、workspace、subprocess、artifact 或安全边界的改动，还应至少抽样运行：

```bash
uv run python examples/run-example.py
grep -RInE 'create_subprocess_shell|shell=True' src tests ui examples || true
```

纯文档改动可只运行 `git diff --check`，但如果文档更新了命令、schema、workspace 路径或 release claims，应抽样运行相关命令确认。

## 主要模块

```text
src/micro_eval/
├── cli/                 # init / validate / run / list / report / ui
├── config/              # loader bridge + RunPlan builder
├── engine/              # AgentAdapter, ExecutionKernel, WorkspaceManager
├── evaluation/          # deterministic validator + human evaluation + optional LLM judge helper
├── decision/            # guarded DecisionReport + pass@k/pass^k aggregation
├── trace/               # optional TraceProvider adapters (process fallback, Langfuse optional)
├── models/              # canonical Pydantic contracts
└── store/               # RunStore / ArtifactStore

ui/src/
├── app/                 # pages and API routes, including /run/[id]/review and trace lookup API
├── components/          # RunList, ResultMatrix, CellDetail, ArtifactViewer, EvaluationPanel, review panels
└── lib/                 # zod schema, fs data access, evaluation append helpers, contract fixture
```

## Canonical 数据流

1. `load_config()` 读取 canonical `configurations[]`；legacy `baseline` / `candidate` 只通过 migration bridge 转换。
2. `build_run_plan()` 展开 `tasks × configurations × repetitions`，生成 `SameStartSnapshot` 与 `ReplayCanonical`。
3. `ExecutionKernel` 为每个 cell 在当前 eval project 的 `.micro-eval/workspaces/{run_id}/{cell_id}/` 下分配 workspace，调用 `AgentAdapter`，写入 stdout/stderr/output artifacts。
4. `validate_cell()` 生成 validator `EvaluationResult` 与 validation evidence；如 `judge.enabled=true`，可追加 supplemental judge evaluation，但不得覆盖 deterministic cell pass/fail。
5. `TraceProvider` 在 `trace.enabled=true` 时收集 `TraceRef`；`process` fallback 不需要 SDK，`langfuse` 通过 optional extra/importlib 接入。
6. `RunStore` 写入 `.micro-eval/runs/{run_id}/run.json` 和 sibling `decision.json`，`ArtifactStore` 写入 `manifest.json`（含 artifacts/evidence/traces）。
7. `build_decision()` 基于 pass@k/pass^k、latency、cost source 与 caveat 生成 guarded `DecisionReport`；snapshot mismatch 降级为 `not_comparable`。
8. UI/API 通过 zod 读取 canonical JSON；human evaluation POST append 到 cell `evaluation.json` 并重算 `decision.json` / `run.json.decision`。

## Workspace boundary

`WorkspaceManager` 是 workspace 路径与生命周期的唯一入口。开发时不要在 adapter、validator、report 或 UI 中自行创建 agent cwd。

当前 MVP 支持三类 task workspace：

| `workspace.type` | Runtime behavior |
| --- | --- |
| `blank` | 在当前 eval project 的 `.micro-eval/workspaces/{run_id}/{cell_id}/` 下创建空目录。 |
| `files` | 将声明的文件/目录复制到 `.micro-eval/workspaces/{run_id}/{cell_id}/`。 |
| `git_repo` | 解析 `ref` 到 commit，并将 detached git worktree 创建到 `.micro-eval/workspaces/{run_id}/{cell_id}/`。 |

安全边界：

- agent cwd 必须位于当前 eval project 的 `.micro-eval/workspaces/{run_id}/{cell_id}/`。
- 不得未经用户明确配置把 agent cwd 放到系统临时目录或项目外目录。
- setup 命令和 agent 命令都必须 argv-only。
- cell workspace cleanup 失败必须进入 snapshot/evidence，而不是静默吞掉。
- raw workspace path 只能作为 snapshot/evidence 路径证据；UI/API 展示 artifact 内容仍必须走 manifest/ref 边界。

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
- **workspace boundary**：agent cwd is the assigned blank/files/git worktree workspace under the current eval project's `.micro-eval/workspaces/`; setup env is allowlisted and does not inherit secrets.
- **output_dir boundary**：`output_dir` must be project-relative and must not contain `..`.
- **artifact safety**：reserved stdout/stderr/output paths are written atomically; symlink, hardlink, non-regular, oversized, and binary artifacts are skipped or represented with warnings/placeholders.
- **raw artifact access**：Decision/UI consume refs and summaries; raw text content is available only through explicit manifest `artifact_id` lookup plus run-dir `realpath` boundary validation.
- **snapshot mismatch**：Decision must stay guarded and never claim strong improvement/regression when comparability is degraded.
- **trace/judge safety**：Trace 和 LLM judge 默认关闭；外部 SDK 只能通过 optional extra/importlib 接入，凭证只用 `MICRO_EVAL_SECRET_*` 环境变量，不写入 config/artifact/release docs。

Workspace 相关改动建议额外检查：

- `tests/e2e/test_p0b_reproducibility_flow.py::test_files_workspace_stays_under_project_workspaces_dir`
- `tests/e2e/test_p0b_reproducibility_flow.py::test_git_repo_workspace_runs_in_isolated_worktree_with_snapshot`
- example smoke 的最新 `cell_snapshot.workspace_path` 是否位于当前 example project 的 `.micro-eval/workspaces/` 下。

## Release readiness checklist

Before claiming a release-ready MVP:

1. Run the verification commands above.
2. Run a deterministic CLI smoke in a temporary project.
3. Build the package with `uv build`.
4. Install the wheel in a Python `>=3.11` virtual environment and run a CLI smoke.
5. Run or review UltraQA adversarial scenarios for normal path, malformed argv, misleading exit code, timeout, secret leakage, artifact traversal, and binary artifact handling.
6. Get independent code-review and architecture review evidence when the release risk warrants it.
7. Record final evidence in `docs/releases/`, generate dependency inventory with `.codex/skills/micro-eval-release/scripts/generate-dependency-inventory.py --version <version>`, and follow `.codex/skills/micro-eval-release/SKILL.md` for version, commit, tag, and dev→main projection gates.
