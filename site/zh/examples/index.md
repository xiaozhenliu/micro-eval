# 示例

micro-eval 附带 5 个源码检出示例，覆盖 43 项已跟踪功能，包括确定性矩阵运行、沙箱化 workspace 隔离、会话评分和 Team Server 工作流。

::: tip 源码检出示例
示例位于代码仓库的 `examples/` 目录下，不随 wheel 包分发。运行前请先克隆仓库。
:::

## 快速开始

在仓库根目录使用跨平台启动器运行任意示例：

::: code-group

```bash [默认 (codefix-showdown)]
python examples/run-example.py
```

```bash [指定示例]
python examples/run-example.py --example multi-task-matrix
python examples/run-example.py --example git-workspace-isolation
python examples/run-example.py --example conversational-eval
python examples/run-example.py --example team-server-quickstart
```

```bash [所有示例]
python examples/run-example.py --example all
```

```bash [真实本地 agent CLI]
# 仅限 codefix-showdown — 需要 Claude Code、Codex CLI 等
python examples/run-example.py --real
```

:::

启动器在检测到 `uv` 时使用 `uv run --project`，否则回退到已安装的 `micro-eval` 命令。运行输出和 `report.html` 会保存在各示例目录下。

## 可用示例

| 示例 | 演示内容 | 核心功能 |
|---|---|---|
| [Agent Codefix Showdown](/zh/examples/agent-codefix-showdown) | 包含真实 agent 和确定性 mock 路径的完整本地代码修复运行 | `files` workspace、3 次 repetition、process trace、pass@k；`eval.blank.yaml` 增加 `blank` workspace 和 `input_mode: file` |
| [Multi-Task Matrix](/zh/examples/multi-task-matrix) | 2 configs × 3 tasks × 2 reps = 12 个 cell，并包含刻意设置的部分失败 candidate | 全部 4 种 expectation 和 setup 命令；`eval.enriched.yaml` 增加高级执行与决策字段 |
| [Git Workspace Isolation](/zh/examples/git-workspace-isolation) | 每个 cell 使用独立 `git_repo` worktree，并演示两次运行的趋势分析 | OS 策略沙箱、fixture digest、toolchain fingerprint、drift breakpoint |
| [Conversational Evaluation](/zh/guide/conversational-evaluation) | 通过 DeepEval ConversationSimulator 进行多轮会话评分 | JSONL subprocess bridge、5 种 conversational metric、结构化 RubricSpec；需要 DeepEval 和 LLM provider |
| [Team Server Quickstart](/zh/guide/team-server) | 使用确定性 mock agent 演示端到端 `micro-eval serve` 工作流 | template、workspace、HTTP enqueue、成员归因、串行队列；需要先执行一次 `cd ui && npm run build` |

## 功能覆盖矩阵

使用下表找到演示目标功能的示例。

`docs` = README 提供了配置片段；该功能无离线 mock 路径。

| 功能 | codefix-showdown | multi-task-matrix | git-workspace-isolation | conversational-eval | team-server |
|---|:---:|:---:|:---:|:---:|:---:|
| 矩阵执行（Tasks × Configs × Reps） | ✓ | ✓ | ✓ | ✓ | |
| 多任务 | | ✓ | ✓ | ✓ | |
| `files` workspace | ✓ | ✓ | | | ✓ |
| `git_repo` workspace | | | ✓ | | |
| `blank` workspace | ✓ (eval.blank) | | | | |
| `exit_code` 期望 | | ✓ | | | |
| `contains` 期望 | ✓ | ✓ | ✓ | | ✓ |
| `file_exists` 期望 | | ✓ | | | |
| `command` 期望 | | ✓ | | | |
| `stdin` input mode | ✓ | ✓ | ✓ | ✓ | ✓ |
| `file` input mode | ✓ (eval.blank) | | | | |
| `stdout` 输出模式 | | docs | ✓ | ✓ | |
| `file` 输出模式 | ✓ | ✓ | | | ✓ |
| `directory` 输出模式 | | docs | | | |
| `setup` 命令 | | ✓ | | | |
| Process trace | ✓ | ✓ | ✓ | ✓ | ✓ |
| OS 策略沙箱 | | | ✓ | | |
| Fixture digest | | | ✓ | | |
| Toolchain fingerprint | | | ✓ | | |
| 趋势分析 + drift breakpoint | | | ✓ | | |
| pass@k / pass^k 聚合 | ✓ | ✓ | ✓ | | |
| Caveat（真实触发） | | ✓ | ✓ | | |
| 人工标注指南 | | | ✓ (README) | | |
| LLM Judge | | | docs | | |
| Langfuse trace | | | docs | | |
| Secrets channel | | | docs | | |
| E2B VM / Modal 容器 | | | docs | | |
| 会话评测 | | | | ✓ | |
| JSONL subprocess bridge | | | | ✓ | |
| 结构化 RubricSpec | | | | ✓ | |
| `randomize_execution_order` | | ✓ (enriched) | | | |
| `skills_profile` | | ✓ (enriched) | | | |
| `parameters` | | ✓ (enriched) | | | |
| `denominator_policy: exclude_failed` | | ✓ (enriched) | | | |
| `inconclusive_policy: block` | | ✓ (enriched) | | | |
| `stop_on_cell_error: true` | | ✓ (enriched) | | | |
| `micro-eval serve` | | | | | ✓ |
| Template management | | | | | ✓ |
| Workspace management | | | | | ✓ |
| HTTP API（evaluate） | | | | | ✓ |
| 成员归因 | | | | | ✓ |
| 串行队列 | | | | | ✓ |
| CSRF 防护 | | | | | ✓ |

## Config Variants

Config variant 可以在不增加 example 目录的情况下扩展功能覆盖：

```bash
# multi-task-matrix：高级执行与决策字段
python examples/multi-task-matrix/run.py --variant enriched

# agent-codefix-showdown：blank workspace 和 file input mode
cd examples/agent-codefix-showdown && uv run micro-eval run --config eval.blank.yaml
```

## 可选外部集成

以下功能需要外部 API Key 或服务，无法离线运行。将相关片段添加到任意示例的 `eval.yaml` 即可启用。完整上下文请参阅各示例的 README。

### LLM Judge（DeepEval）

```yaml
judge:
  enabled: true
  provider: deepeval
  model: "gpt-4o"
  temperature: 0.0
  pass_threshold: 0.5
  required_secrets: [MICRO_EVAL_SECRET_OPENAI_KEY]
```

```bash
export MICRO_EVAL_SECRET_OPENAI_KEY=sk-...
```

### Langfuse Trace

```yaml
trace:
  enabled: true
  provider: langfuse
```

```bash
export LANGFUSE_PUBLIC_KEY=...
export LANGFUSE_SECRET_KEY=...
export LANGFUSE_HOST=https://cloud.langfuse.com
```

### Secrets Channel

在 agent spec 中声明所需 secrets，micro-eval 会在运行时注入其值，并自动从所有日志和 trace 中将其脱敏：

```yaml
agent:
  required_secrets: [MICRO_EVAL_SECRET_MY_KEY]
```

所有 secrets 在环境变量中必须以 `MICRO_EVAL_SECRET_` 为前缀。完整示例参见 [Git Workspace Isolation](/zh/examples/git-workspace-isolation)。

### 远程隔离：E2B VM / Modal 容器

在 Git Workspace Isolation 示例中保留既有工作区来源，使用 `vm` 选择 E2B，或使用 `container` 选择 Modal：

```yaml
workspace:
  type: git_repo
  path: fixture-repo
  ref: HEAD
  isolation_level: vm  # Modal 使用 container
  trust_level: untrusted
  network_policy: none
```

安装所选 provider 的 extra，并设置宿主侧控制凭据：

```bash
# E2B（isolation_level: vm）
uv pip install 'micro-eval[e2b]'
export MICRO_EVAL_SECRET_E2B_API_KEY=e2b_...

# Modal（isolation_level: container）
uv pip install 'micro-eval[modal]'
export MICRO_EVAL_SECRET_MODAL_TOKEN_ID=...
export MICRO_EVAL_SECRET_MODAL_TOKEN_SECRET=...
```

`micro-eval[remote]` 同时安装两个 SDK。控制凭据不属于 agent 的 `required_secrets`。缺少 SDK 或凭据会使 cell 失败；两个远程 provider 都不会回退本机。

示例的 `command: ["{python}", "scripts/mock-refactor-agent.py"]` 使用沙箱中的 `python3` 和上传的 fixture 脚本。真实 agent 命令也必须已安装在远程运行环境中，或随工作区提供。不能直接复用宿主 Codex 或其他 CLI 的绝对路径。如果 setup 或 agent 需要访问包仓库或模型 API，请显式设置 `network_policy: full`；`none` 阻止出站访问，`allowlist` 会被拒绝。

远程 `git_repo` 传输固定 ref 的文件，不包含 `.git` 历史。setup、agent 和 command validator 共享同一个沙箱。远程 git observation 当前不可用，因此 run 记录 caveat，不会声称已验证同起点。离线 SDK contract 测试与可选的带凭据 live 检查分别记录。
