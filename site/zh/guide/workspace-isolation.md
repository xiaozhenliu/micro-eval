# 工作区隔离

可复现的起点是 micro-eval 的核心价值主张。如果两次运行从不同的工作区状态出发，即使其他所有参数完全相同，其结果也无法进行有意义的比较。工作区隔离是确保结果矩阵中每个单元格都以已知、一致的起点执行的机制。

::: tip 自 v0.3.0 起
工作区类型和隔离级别在 Phase 3 中引入。更早的版本隐式使用逻辑隔离（git worktree）。现在，所有四个级别均可显式配置。
:::

## 为什么这很重要

当你运行 `Tasks × Configurations × Repetitions` 时，每个单元格都在自己的工作区中执行。如果没有隔离：

- 写入文件的任务会污染下一次重复执行的环境
- 两个共享工作区的 configuration 会产生相关联的结果
- 如果仓库发生漂移，不同日期的运行结果将无法比较

micro-eval 为每次运行记录一个 `SameStartSnapshot`——一组可比性维度，只有所有维度都匹配时，两次运行才被视为可直接比较。工作区状态是该快照中的一等维度。

## 工作区类型

task 上的 `workspace` 字段定义了 agent 启动时所面对的环境。

### `blank`

一个空的临时目录。适用于不需要预先存在文件的任务——纯生成任务、API 调用，或自行创建脚手架的任务。

```yaml
workspace:
  type: blank
  isolation_level: logical
```

### `files`

在执行前将指定的文件和目录复制到任务工作区。文件路径相对于 task YAML 文件解析。

```yaml
workspace:
  type: files
  files:
    - ./fixtures/src/utils.py
    - ./fixtures/tests/test_utils.py
    - ./fixtures/pyproject.toml
  isolation_level: logical
```

::: tip Fixture 摘要
使用 `files` 时，micro-eval 会在运行时计算每个源文件的 SHA-256 摘要，并将其记录在 `SameStartSnapshot.fixture_digests` 中。只有 fixture 摘要匹配的两次运行才具有可比性。
:::

### `git_repo`

在指定 ref 处创建一个隔离的 git worktree。这是代码编辑任务最具可复现性的选项——agent 获得真实的 git 历史记录，可以创建分支，其改动完全与你的工作树隔离。

```yaml
workspace:
  type: git_repo
  path: .                          # path to the repo (relative to task YAML)
  ref: "abc1234"                   # pin to a specific commit
  isolation_level: logical
  setup:                           # optional: run inside the worktree before the agent starts
    - ["uv", "sync"]
```

::: warning 锁定 ref
对于打算随时间进行比较的评测，请始终将 `ref` 设为完整的 commit SHA。如果省略 `ref`，micro-eval 会在运行时使用 `HEAD`——随着仓库演进，工作区会发生漂移，导致历史比较不可靠。
:::

## 隔离级别

workspace 上的 `isolation_level` 字段控制 agent 进程被约束的严格程度。

| 级别 | 名称 | 后端 | 可用性 |
|-------|------|---------|--------------|
| 0 | `logical` | Git worktree | 始终可用 |
| 1 | `os_policy` | Seatbelt (macOS) / Bubblewrap (Linux) | 取决于宿主 OS |
| 3 | `container` | 保留 | 未来 |
| 4 | `vm` | E2B / Modal | 需要凭证 |

### 级别 0 — `logical`

默认级别。agent 进程以你的完整用户权限运行，但接收一个隔离的 git worktree 作为其工作目录。改动被限制在 worktree 中，不会影响你的工作树。

适用于针对自己仓库运行的受信任 agent（你自己的代码）。

```yaml
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: main
  isolation_level: logical
```

### 级别 1 — `os_policy`

在 agent 进程周围添加 OS 级别的沙箱策略。此级别可防止 agent 意外（或故意）读取 `~/.ssh` 中的密钥、向工作区外的路径写入，或修改你的全局配置文件。

```yaml
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: main
  isolation_level: os_policy
  trust_level: semi_trusted
  network_policy: allowlist
```

::: warning 降级至 logical
如果请求 `os_policy` 但宿主机上 Seatbelt 或 Bubblewrap 不可用（例如，未安装 `bwrap` 的 Linux），micro-eval 会**降级至 `logical`** 并在运行结果中记录一个 `mixed_isolation` 告警。运行不会中止，但该告警会在 UI 中显示，并在严格可比性检查中被排除。
:::

### 级别 4 — `vm`（远程执行）

在 E2B 或 Modal 提供的远程 VM 内运行 agent。这是最高隔离级别，适用于：

- 不受信任或对抗性的 agent
- 无论宿主 OS 如何都需要干净 Linux 环境的 agent
- 需要特定 OS 包或内核特性的任务

```yaml
workspace:
  type: blank
  isolation_level: vm
  trust_level: untrusted
  network_policy: none
```

::: danger 远程 provider 会直接失败
与 `os_policy` 不同，远程 provider（`e2b`、`modal`）**不会**静默降级。如果凭证缺失或 provider 不可达，运行会立即以错误终止。这是故意为之——从 `vm` 静默降级到 `logical` 会使远程隔离的目的完全落空。

在运行前设置所需的环境变量作为凭证：
:::

```bash
export MICRO_EVAL_SECRET_E2B_API_KEY="your-e2b-key"
export MICRO_EVAL_SECRET_MODAL_TOKEN_ID="your-modal-token-id"
export MICRO_EVAL_SECRET_MODAL_TOKEN_SECRET="your-modal-token-secret"
```

以 `MICRO_EVAL_SECRET_` 为前缀的密钥会自动从日志、运行产物和 LLM judge 提示词中脱敏。

## 信任级别

`trust_level` 字段传达意图，由 provider 注册表用于验证所选隔离级别是否合适。

| 信任级别 | 推荐隔离 | 典型用途 |
|-------------|----------------------|------------------|
| `trusted` | `logical` | 你自己的 agent、内部工具 |
| `semi_trusted` | `os_policy` | 你已审查过的第三方 agent |
| `untrusted` | `vm` | 下载的 agent、外部贡献者 |
| `adversarial` | `vm` | 红队测试、可能尝试逃逸的 agent |

::: warning 信任是建议性的，不是强制性的
设置 `trust_level: adversarial` 不会自动升级隔离级别。你还必须设置 `isolation_level: vm`。信任用于文档、可比性元数据和未来的策略执行——本身不作为安全门控。
:::

## 网络策略

workspace 上的 `network_policy` 字段控制 agent 进程的出站网络访问。它在级别 1 及以上生效。

| 策略 | 行为 |
|--------|----------|
| `full` | 无网络限制（级别 0 的默认值） |
| `allowlist` | 仅 `network_allowlist` 中列出的域名可达 |
| `none` | 阻止所有出站网络访问 |

```yaml{6-10}
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: main
  isolation_level: os_policy
  trust_level: semi_trusted
  network_policy: allowlist
```

## SameStartSnapshot：可比性维度

每次运行都会记录一个 `SameStartSnapshot`——产生结果的条件指纹。只有所有维度都匹配时，两次运行才被视为可直接比较。

| 维度 | 捕获内容 |
|-----------|-----------------|
| `workspace_type` | `blank`、`files` 或 `git_repo` |
| `git_commit` | 锁定的 commit SHA（针对 `git_repo` 工作区） |
| `fixture_digests` | 每个源文件的 SHA-256（针对 `files` 工作区） |
| `sandbox_policy` | `logical`、`os_policy`、`vm` 等 |
| `network_policy` | `full`、`allowlist` 或 `none` |
| `toolchain_fingerprint` | Python 版本、uv lockfile 哈希、关键二进制版本 |
| `config_hash` | 本次运行所用 configuration 块的哈希 |

当你在趋势分析页面比较运行结果时，micro-eval 会将任何存在维度差异的对标记为 `not_comparable`，并显示哪个维度发生了偏差。

## 完整配置示例

::: code-group

```yaml [logical — trusted agent]
configurations:
  - id: claude-code-v1
    agent:
      command: ["claude", "--dangerously-skip-permissions"]
      input_mode: stdin
      timeout_s: 120

tasks:
  - tasks/add-docstrings.yaml
```

```yaml [tasks/add-docstrings.yaml]
id: add-docstrings
name: Add docstrings
input_payload: "Add Google-style docstrings to every public function in src/parser.py."
workspace:
  type: git_repo
  path: .
  ref: "a1b2c3d"
  isolation_level: logical
  trust_level: trusted
```

```yaml [os_policy — semi-trusted agent]
configurations:
  - id: external-agent
    agent:
      command: ["./bin/external-agent", "--mode", "edit"]
      input_mode: stdin
      timeout_s: 180

tasks:
  - tasks/implement-feature.yaml
```

```yaml [tasks/implement-feature.yaml]
id: implement-feature
name: Implement feature
input_payload: "Implement the feature described in SPEC.md."
workspace:
  type: files
  files:
    - ./fixtures/SPEC.md
    - ./fixtures/src/
    - ./fixtures/tests/
  isolation_level: os_policy
  trust_level: semi_trusted
  network_policy: allowlist
expectations:
  - type: exit_code
    value: 0
  - type: file_exists
    path: src/feature.py
```

```yaml [vm — untrusted agent]
configurations:
  - id: red-team-agent
    agent:
      command: ["./downloaded-agent"]
      input_mode: stdin
      timeout_s: 300
    required_secrets:
      - MICRO_EVAL_SECRET_E2B_API_KEY

tasks:
  - tasks/code-challenge.yaml
```

```yaml [tasks/code-challenge.yaml]
id: code-challenge
name: Code challenge
input_payload: "Solve the algorithmic problem in challenge.txt."
workspace:
  type: files
  files:
    - ./fixtures/challenge.txt
  isolation_level: vm
  trust_level: adversarial
  network_policy: none
expectations:
  - type: contains
    value: "SOLVED"
```

:::

---

## 服务器模式：工作区级隔离

在服务器模式（`micro-eval serve`）下，单元格级 workspace 隔离之上还有一层额外的隔离：

**服务器工作区**是位于 `~/.micro-eval-server/workspaces/<workspace-id>/` 下的隔离目录。每个工作区：

- 拥有独立的 `eval.yaml`、`tasks/` 和 `.micro-eval/runs/`
- 作为 ExecutionKernel 的 `project_root`——单元格级 worktree 隔离在其内部的工作方式完全相同
- 归属于某个成员（在创建时记录，不可变更）
- 拥有独立的趋势索引（`index.db`）

这意味着在服务器模式下存在**两层** workspace 隔离：

| 层级 | 范围 | 机制 |
|-------|-------|-----------|
| 服务器工作区 | 每个成员的评测环境 | `~/.micro-eval-server/workspaces/` 下的目录隔离 |
| 单元格工作区 | 每个单元格的执行沙箱 | `.micro-eval/workspaces/<run>/<cell>/` 下的 Git worktree / blank / files |

API 路由强制执行工作区边界：对 `/api/workspaces/[id]/runs/...` 的请求只能访问该工作区内的 run。路径遍历尝试会被格式校验和路径包含性检查拒绝。

## 下一步

- [趋势分析](/zh/guide/trend-analysis) — 追踪评测结果随时间的变化，检测回归，并标注漂移断点
