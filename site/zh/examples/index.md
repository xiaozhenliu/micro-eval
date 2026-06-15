# 示例

micro-eval 附带一组源码检出示例，覆盖工具的完整功能面——从简单的单任务冒烟测试，到多单元矩阵，再到 Phase 3 沙箱化 workspace 隔离。

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
| [Agent Codefix Showdown](/zh/examples/agent-codefix-showdown) | 使用真实 agent 矩阵的完整 MVP 流程 | `files` workspace、argv 命令、Phase 2 trace、pass@k |
| [Multi-Task Matrix](/zh/examples/multi-task-matrix) | 2 × 3 × 2 = 12 个单元的矩阵 | 全部 4 种期望类型、setup 命令、`inconclusive` 决策 |
| [Git Workspace Isolation](/zh/examples/git-workspace-isolation) | Phase 3 workspace + 趋势分析 | git worktree、OS 沙箱、fixture digest、趋势漂移 |

## 功能覆盖矩阵

使用下表找到演示目标功能的示例。

`docs` = README 提供了配置片段；该功能无离线 mock 路径。

| 功能 | codefix-showdown | multi-task-matrix | git-workspace-isolation |
|---|:---:|:---:|:---:|
| 矩阵执行（Tasks × Configs × Reps） | ✓ | ✓ | ✓ |
| 多任务 | | ✓ | ✓ |
| `files` workspace | ✓ | ✓ | |
| `git_repo` workspace | | | ✓ |
| `exit_code` 期望 | | ✓ | |
| `contains` 期望 | ✓ | ✓ | ✓ |
| `file_exists` 期望 | | ✓ | |
| `command` 期望 | | ✓ | |
| `stdout` 输出模式 | | docs | ✓ |
| `file` 输出模式 | ✓ | ✓ | |
| `directory` 输出模式 | | docs | |
| `setup` 命令 | | ✓ | |
| 进程 trace | ✓ | | |
| OS 策略沙箱 | | | ✓ |
| Fixture digest | | | ✓ |
| Toolchain fingerprint | | | ✓ |
| 趋势分析 + drift breakpoint | | | ✓ |
| pass@k / pass^k 聚合 | ✓ | ✓ | ✓ |
| Caveat（真实触发） | | ✓ | ✓ |
| 人工标注指南 | | | ✓ |
| LLM Judge | | | docs |
| Langfuse trace | | | docs |
| Secrets channel | | | docs |
| E2B/Modal 远程 VM | | | docs |

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

### E2B / Modal 远程 VM

将任意任务的隔离级别升级为 `vm`，即可使用完整的远程沙箱执行：

```yaml{3-4}
workspace:
  type: git_repo
  isolation_level: vm
  trust_level: untrusted
```

```bash
export E2B_API_KEY=e2b_...
# 或者
export MODAL_TOKEN_ID=...
export MODAL_TOKEN_SECRET=...
```

::: warning 不会静默降级
远程 VM provider（`E2B`、`Modal`）在凭证缺失时会直接报错退出，不会自动回退到更低的隔离级别——这是有意为之，以防止环境漂移被悄然忽视。
:::
