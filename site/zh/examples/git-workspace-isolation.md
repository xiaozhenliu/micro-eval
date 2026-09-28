# Git Workspace 隔离

micro-eval 最完整的示例。在单个可运行场景中演示 Phase 3 的所有 workspace 能力：每个 cell 独立的 git worktree 隔离、OS 策略沙箱、记录进 `SameStartSnapshot` 的 fixture digest 与 toolchain fingerprint，以及带 drift breakpoint 的跨 run 趋势分析。

::: tip 需要先克隆仓库
本示例位于仓库的 `examples/git-workspace-isolation/` 目录下。运行前请先克隆仓库 —— 它不包含在安装包中。
:::

## 你将学到什么

- `git_repo` workspace 类型如何为每个评测 cell 提供独立的 git worktree
- OS 策略沙箱（macOS 上的 `Seatbelt`，Linux 上的 `Bubblewrap`）如何包裹 agent 进程 —— 以及在两者都不可用时如何优雅降级
- `fixture_digests` 和 `toolchain_fingerprint` 如何流入 `SameStartSnapshot`，以证明两次 run 是可比较的
- 两次拥有不同 configuration digest 的 run 如何在趋势图中产生 drift breakpoint
- 如何通过 Web UI 为单个 cell 添加人工评分和备注

## 运行示例

::: code-group

```bash [两次 run + 报告]
python examples/git-workspace-isolation/run.py
```

```bash [启动 Web UI]
python examples/git-workspace-isolation/run.py --ui
```

```bash [仅生成报告（复用已有 run）]
python examples/git-workspace-isolation/run.py --skip-run
```

:::

脚本的执行流程：

1. 将 `fixture-repo/` 初始化为 git 仓库（仅首次运行时执行）
2. 使用 `eval.mock.yaml` 执行 Pass 1 —— `timeout_s: 60`，基准 config digest
3. 使用 `eval.mock.v2.yaml` 执行 Pass 2 —— `timeout_s: 120`，不同的 config digest，触发 drift breakpoint
4. 生成文本报告和 `report.html`

## git\_repo Workspace

结果矩阵中的每个评测 cell —— 即每个 `(task, configuration, repetition)` 三元组 —— 都通过 `git worktree add --detach` 获得一份独立的 fixture 仓库副本。

### Task 配置

本示例中的两个 task 共享相同的 workspace 声明：

```yaml{3-9}
workspace:
  type: git_repo
  path: fixture-repo
  ref: HEAD
  fixtures:
    - path: fixture-repo/app.py
  toolchain:
    runtime: python3
    lockfile: requirements.txt
  isolation_level: os_policy
  trust_level: semi_trusted
  network_policy: none
```

### 运行时行为

对于每个 cell，micro-eval 会执行：

```bash
git worktree add --detach .micro-eval/workspaces/<cell-id> <commit>
```

agent 的工作目录被设置为该 worktree 的根目录。由于每个 cell 都从完全相同的 `ref: HEAD` commit 开始：

- 一个 agent 所做的修改对所有其他 agent 都不可见
- 源仓库 `fixture-repo/` 和其他 cell 的 worktree 均不会被触及
- 所有 cell 都从可证明的相同代码状态启动（以 `fixture_digests` 记录在 `SameStartSnapshot` 中）

::: tip Agent 脚本位于 fixture 仓库内
本示例的 mock agent 位于 `fixture-repo/scripts/`。由于 agent 的 cwd 是 worktree 根目录（即 `fixture-repo/` 的副本），脚本在每个 worktree 中都可直接使用，无需额外配置。
:::

::: warning 需要 git
`git_repo` workspace 类型要求 `PATH` 中存在 `git`。runner 在启动时会检查这一点，如果缺失则会以清晰的错误信息退出。
:::

## OS 策略沙箱

在 workspace 配置中只需一行改动，即可启用 OS 级进程隔离：

```yaml{4-6}
workspace:
  type: git_repo
  path: fixture-repo
  isolation_level: os_policy
  trust_level: semi_trusted
  network_policy: none
```

### 各平台行为

| 平台 | Provider | 机制 |
|---|---|---|
| macOS | Seatbelt | 默认拒绝的沙箱 profile 包裹 agent 进程 |
| Linux | Bubblewrap | `bwrap` 命名空间隔离 |
| 两者均不可用 | Logical（降级） | 仅 git worktree 隔离 + 记录 caveat |

::: warning OS provider 不可用
如果在选择前 Seatbelt 和 Bubblewrap 均不可用，micro-eval 降级为 `logical`，并记录 snapshot-gate caveat，例如 `requested isolation os_policy unavailable on Linux; ran at logical`。已选定的 provider 启动或执行失败时，不会在沙箱外重试。
:::

`same_start_snapshot.sandbox_policy` 记录请求的隔离级别。判断隔离效果或可比性前，应查看每个 cell 的 workspace evidence 中实际 `provider`、`network_effective`，以及 `snapshot_gate_result.caveats`。OS 策略将宿主写入限制在 cell 工作区和输出 staging，但不保护可读宿主文件的保密性。

## Fixture Digest 与 Toolchain Fingerprint

micro-eval 在每次 `git_repo` run 的 `SameStartSnapshot` 中记录两项可比性证明。

### Fixture digest

从 `git_repo` workspace 路径和被评测的 commit（本示例中为 `HEAD`）推导得出。micro-eval 对该 commit 下的 fixture 仓库目录树计算 SHA-256，并将其记录为 `fixture_digests`。

```json
{
  "same_start_snapshot": {
    "fixture_digests": {
      "fixture-repo": "sha256:4a7c3b..."
    }
  }
}
```

如果对相同的 task 运行两次，`fixture_digests` 的值将完全相同 —— 这证明两次 run 看到的是相同的代码。

### Toolchain fingerprint

在 task 的 workspace `toolchain` 块中声明：

```yaml
toolchain:
  runtime: python3
  lockfile: requirements.txt
```

micro-eval 对 `python3` 二进制文件和 `requirements.txt` 的内容进行哈希，并将结果记录为 `toolchain_fingerprint`。

```json
{
  "same_start_snapshot": {
    "toolchain_fingerprint": "sha256:f8e2a1..."
  }
}
```

`fixture_digests` 和 `toolchain_fingerprint` 共同为以下问题提供可验证的答案：*两次 run 是否从相同的环境出发？*

## 趋势分析与 Drift Breakpoint

本示例刻意创建了两次拥有不同 configuration digest 的 run，以演示漂移检测机制。

| Pass | 配置文件 | `timeout_s` | Config digest |
|---|---|---|---|
| 1 | `eval.mock.yaml` | `60` | `abc...`（基准） |
| 2 | `eval.mock.v2.yaml` | `120` | `def...`（已变更） |

由于 `timeout_s` 发生了变化，Pass 2 的 configuration digest 与 Pass 1 不同。micro-eval 在 Pass 2 上记录一条 drift caveat，并在趋势图中的两次 run 之间标注一个 **drift breakpoint** —— 这是一个视觉信号，表明断点两侧的结果不可直接比较。

### 查询 trends API

启动 Web UI 后（`python run.py --ui`），查询 `refactor-agent-v1` configuration 的趋势数据：

```bash
curl "http://localhost:3000/api/trends?config_id=refactor-agent-v1"
```

响应中包含一个 `breakpoints` 数组，标记了 config digest 发生变化的位置：

```json
{
  "config_id": "refactor-agent-v1",
  "data_points": [ ... ],
  "breakpoints": [
    {
      "between_runs": ["run-001", "run-002"],
      "reason": "config_digest_changed",
      "caveat": "timeout_s changed from 60 to 120"
    }
  ]
}
```

::: tip 如何解读 drift breakpoint
drift breakpoint 并不意味着结果是错误的 —— 它意味着你不应该跨越断点比较通过率，就好像条件完全相同一样。以断点为基准锚定分析：config 变更后的提升，是*在新配置下*的提升。
:::

## 人工标注指南

Web UI 允许你为结果矩阵中的任意 cell 附加人工评分和备注。标注内容会持久化保存到 run 目录下的 `evaluation.json`，并在后续重新生成报告时一并包含。

**第 1 步 —— 启动 Web UI**

```bash
python examples/git-workspace-isolation/run.py --ui
```

**第 2 步 —— 打开 run 页面**

访问 `http://localhost:3000`，从列表中点击一个 run。

**第 3 步 —— 选择 cell**

点击结果矩阵中的任意 cell（由 task × configuration × repetition 标识）。

**第 4 步 —— 添加标注**

在右侧的 **AnnotationPanel** 中填写：
- **Score** —— `0.0`（失败）到 `1.0`（通过）之间的值
- **Comment** —— 自由文本形式的分析或观察

**第 5 步 —— 保存**

点击 **Save**。标注内容会立即写入 `evaluation.json`。

**第 6 步 —— 重新生成报告**

```bash
# 在示例目录下执行：
micro-eval report --format text
```

重新生成的报告中，标注评分和备注会与自动验证器的结果并排显示。

::: tip 标注与自动评分
人工标注不会取代确定性验证器 —— 而是叠加在其之上。一个 cell 可以自动通过 `contains` 检查，同时在输出质量较差时仍被赋予较低的人工评分。
:::

## 文件结构

```
git-workspace-isolation/
├── run.py                          # 一键运行脚本：git init + 两次 pass + 报告
├── eval.mock.yaml                  # Pass 1：timeout_s=60（基准 config digest）
├── eval.mock.v2.yaml               # Pass 2：timeout_s=120（触发 drift breakpoint）
├── tasks/
│   ├── refactor-extract-function.yaml   # 从 app.py 中提取辅助函数
│   └── add-type-hints.yaml              # 为 app.py 添加类型注解
├── fixture-repo/                   # 由 run.py 在首次运行时初始化为 git 仓库
│   ├── app.py                      # 60 行的单体函数（源材料）
│   ├── requirements.txt            # toolchain fingerprint 来源
│   ├── tests/
│   │   └── test_app.py             # app.py 的 pytest 测试
│   ├── .gitignore
│   └── scripts/
│       ├── mock-refactor-agent.py  # 读取 stdin，提取辅助函数，输出 REFACTOR_COMPLETE
│       └── mock-typehint-agent.py  # 读取 stdin，添加类型注解，输出 TYPE_HINTS_ADDED
└── README.md
```

micro-eval 创建的每个 worktree 都放置在 `.micro-eval/workspaces/<cell-id>/` 下，run 完成后自动清理。

## 可选集成

以下集成需要外部凭证。将对应的配置片段添加到 `eval.mock.yaml`（或 `eval.mock.v2.yaml`）即可启用。

### LLM Judge

通过 DeepEval 启用 LLM judge，对 agent 输出质量进行超越 `contains` 检查的评分：

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

将成本和延迟数据路由到 Langfuse，实现跨 run 的可观测性：

```yaml
trace:
  enabled: true
  provider: langfuse
```

```bash
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_HOST=https://cloud.langfuse.com
```

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
