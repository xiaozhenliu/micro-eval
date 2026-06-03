# micro-eval

Current version: `0.1.3`

`micro-eval` 是面向 1–20 人 AI 小团队的本地 Agent / Skill 评测助手。它把“我感觉 candidate 更强”变成“同一任务、同一起点、同一证据链下，它在哪些 cell 上更强/更弱、为什么、延迟多少、是否值得继续投”。

MVP 聚焦本地可复现对比：自写执行层负责 subprocess 编排、并发、超时、workspace 隔离和结果收集；评分/观测底座通过适配层逐步接入，DeepEval 不作为 test runner，Langfuse/OpenHands 不在 MVP 强依赖路径内。

## MVP Golden Path

在一个准备评测的本地项目目录中运行：

```bash
micro-eval init --force
micro-eval validate
micro-eval run --max-concurrency 2
micro-eval list
micro-eval report --format text
micro-eval report --format html --output report.html
micro-eval ui --port 3000
```

然后在 Web UI 中查看：Run List → Decision Summary → Result Matrix → Cell Evidence → Artifact Viewer → Human Evaluation → Decision/Caveats。

### Ready-to-run example

如果你想先体验完整 MVP 流程、但还不想自己准备 `eval.yaml` 和 task，使用源码仓库中的示例：

```bash
uv run micro-eval validate --config examples/agent-codefix-showdown/eval.mock.yaml
uv run micro-eval run --config examples/agent-codefix-showdown/eval.mock.yaml --max-concurrency 1
cd examples/agent-codefix-showdown
uv run --project ../.. micro-eval list
uv run --project ../.. micro-eval report --format text
uv run --project ../.. micro-eval report --format html --output report.html
```

真实 agent 矩阵见 [`examples/agent-codefix-showdown/`](examples/agent-codefix-showdown/)；它覆盖 Claude Code、Codex CLI、OpenClaw 和 Hermes，并说明当前 source-checkout/UI 限制。示例索引见 [`examples/`](examples/)。

## 核心特性

- **Canonical configuration matrix**：`tasks × configurations × repetitions` 展开为 `RunPlan` / `RunCell`。
- **自写执行层**：asyncio bounded concurrency、单 cell timeout、失败不阻塞其它 cell。
- **安全 argv subprocess**：canonical `agent.command` 必须是 argv list；legacy string command 只通过 migration bridge 转换并产生 warning。
- **同起点证据**：`SameStartSnapshot`、`CellSnapshot`、`SnapshotGateResult` 和 `ReplayCanonical` 写入 run 产物。
- **Workspace 隔离**：支持 `blank` / `files` / `git_repo`；`git_repo` task 通过 git worktree 执行，agent cwd 是分配 workspace。
- **Artifact / Evidence 链**：`.micro-eval/runs/{run_id}/manifest.json` 索引 `ArtifactRef` 与 `EvidenceItem`。
- **Deterministic validation**：支持 `exit_code`、`contains`、`file_exists`、`command` expectation；`command` 也是 argv-only。
- **人工评分持久化**：UI 通过 POST API append human `EvaluationResult`，不把 `localStorage` 当可信评分来源。
- **Guarded decision**：snapshot mismatch 会降级为 `not_comparable` / `inconclusive`，不会伪造强结论。
- **本地 UI/API**：Next.js 本地 UI 通过 zod 解析 canonical run/cell/artifact/evaluation 数据。

## 安装

要求：Python `>=3.11`、Node.js/npm（仅运行 Web UI 时需要）。

```bash
uv pip install -e .
# 开发/测试可选
uv pip install -e ".[dev,scoring,observability]"
```

UI：

```bash
cd ui
npm install
npm run dev
```

从源码运行时也可以使用：

```bash
uv run micro-eval --help
```

## CLI 命令

| 命令 | 行为 |
|---|---|
| `micro-eval init [--force]` | 生成 canonical `eval.yaml`、`tasks/hello.yaml` 和 `tasks/templates/` starter templates。 |
| `micro-eval validate [--format text\|json]` | 只加载 config/tasks 并构建 RunPlan，输出可操作诊断，不运行 agent。 |
| `micro-eval run [--config eval.yaml] [--max-concurrency N] [--dry-run] [--format text\|json]` | 执行矩阵 run 或输出 RunPlan。 |
| `micro-eval list [--format text\|json]` | 列出 `.micro-eval/runs/*/run.json`。 |
| `micro-eval report [--run RUN_ID] [--format text\|json\|html]` | 输出矩阵、Basic Honest Stats、decision/caveats/artifacts。 |
| `micro-eval ui [--port 3000]` | 启动本地 Next.js UI。 |

Config 查找顺序：`--config` > `$MICRO_EVAL_CONFIG` > `./eval.yaml`。

## Canonical `eval.yaml`

```yaml
project_name: demo-agent-eval
description: Local deterministic starter project

configurations:
  - id: baseline
    name: echo-baseline
    role: baseline
    repetitions: 1
    agent:
      name: echo-baseline
      command: ["cat"]
      input_mode: stdin
      output_mode: stdout
      timeout_s: 10
      env: {}
      required_secrets: []
  - id: candidate
    name: echo-candidate
    role: candidate
    repetitions: 1
    agent:
      name: echo-candidate
      command: ["cat"]
      input_mode: stdin
      output_mode: stdout
      timeout_s: 10
      env: {}
      required_secrets: []

tasks:
  - tasks/hello.yaml
output_dir: .micro-eval/runs

guardrails:
  max_concurrency: 2
  timeout_s: 30
  output_cap_bytes: 1048576
  artifact_cap_bytes: 1048576
  stop_on_cell_error: false

evaluation:
  comparison_subject: "candidate vs baseline"
  task_set_version: ""
  success_criteria:
    - Deterministic validator expectations pass.
    - Human evaluator reviews caveats before deciding.
  budget: null
  decision_threshold: null
  inconclusive_policy: warn
  min_repetitions: 1
  required_evaluators: [validator]
  denominator_policy: include_failed
```

Legacy `baseline` / `candidate` configs still load through an explicit migration bridge, but new projects should use `configurations[]`.

## Task YAML

```yaml
id: hello
name: Hello echo
description: Verify a local agent can echo stdin.
input_payload: "Hello, micro-eval!"
expected_output: "Hello, micro-eval!"
expectations:
  - type: contains
    stream: output
    value: "Hello, micro-eval!"
workspace:
  type: blank
rubric: Output should contain the input exactly.
business_impact_tier: 3
tags: [smoke, deterministic]
```

Workspace types:

- `blank`：每个 cell 使用临时空目录。
- `files`：复制声明的文件/目录到临时 workspace。
- `git_repo`：从 `workspace.path` / `workspace.ref` 创建 isolated git worktree。

Expectation types:

- `exit_code`
- `contains`
- `file_exists`
- `command`：必须是 argv list，cwd 限制在 cell output dir 内。

## Result layout

```text
.micro-eval/runs/{run_id}/
├── run.json
├── manifest.json
└── cells/{cell_id}/
    ├── result.json
    ├── stdout.txt
    ├── stderr.txt
    ├── output.txt          # when output exists
    └── evaluation.json     # validator + appended human evaluations
```

`DecisionReport` 回溯链：`decision.evaluation_refs → EvaluationResult.evidence_refs → EvidenceItem.artifact_refs/source_ref → ArtifactRef.path`。

## Secrets

MVP secrets 只来自环境变量，且必须以 `MICRO_EVAL_SECRET_` 开头，并由 configuration 显式声明：

```yaml
agent:
  required_secrets: [MICRO_EVAL_SECRET_TOKEN]
```

只有显式声明的 secrets 会注入 agent env；所有宿主环境中非空的 `MICRO_EVAL_SECRET_*` 值都会参与 stdout/stderr/text artifact/evidence/human-comment redaction，持久化前替换为 `[REDACTED:<NAME>]`。

## Web UI

```bash
MICRO_EVAL_PROJECT_ROOT=/path/to/eval-project npm run dev
```

UI 路由：

- `/`：Run List
- `/run/[id]`：Decision Summary、Caveats、Result Matrix、Cell Evidence、Human Evaluation
- `/run/[id]/artifact/[artifactId]`：按 manifest `artifact_id` 查看 artifact
- `/api/runs/...`：read-only run/cell/artifact API + append-only human evaluation API

Artifact API 只接受 manifest 中存在的 `artifact_id`，并通过 run-dir `realpath` 边界校验；binary/oversized/skipped artifacts 会返回 warning/placeholder，而不是原始内容。

## Release evidence

当前 release 流程和 v0.1.3 证据记录在：

- `docs/engineering/release-process.md`
- `docs/releases/2026-06-03-v0.1.3-release-evidence.md`
- `docs/releases/2026-06-03-v0.1.3-dependency-inventory.md`
- `docs/releases/2026-06-02-mvp-release-evidence.md`（MVP readiness 历史证据）

最终门禁包括 version consistency、compileall、pytest、UI lint/build、`uv build`、`git diff --check` / `git diff --cached --check`、security greps、release evidence、dependency inventory 和 dev→main projection 验证。

## 验证命令

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
