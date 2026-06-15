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
tasks:
  - id: generate-readme
    prompt: "Write a README.md for a Python CLI tool called 'greet'."
    workspace:
      type: blank
```

### `files`

在执行前将指定的文件和目录复制到任务工作区。源路径相对于配置文件解析。

```yaml
tasks:
  - id: refactor-utils
    prompt: "Refactor the helper functions in utils.py to reduce duplication."
    workspace:
      type: files
      sources:
        - path: src/utils.py
        - path: tests/test_utils.py
        - path: pyproject.toml
```

::: tip Fixture 摘要
使用 `files` 时，micro-eval 会在运行时计算每个源文件的 SHA-256 摘要，并将其记录在 `SameStartSnapshot.fixture_digests` 中。只有 fixture 摘要匹配的两次运行才具有可比性。
:::

### `git_repo`

在指定 commit 处创建一个隔离的 git worktree。这是代码编辑任务最具可复现性的选项——agent 获得真实的 git 历史记录，可以创建分支，其改动完全与你的工作树隔离。

```yaml
tasks:
  - id: fix-issue-42
    prompt: "Fix the bug described in issue #42. The relevant code is in src/parser.py."
    workspace:
      type: git_repo
      repo: .                      # path to the repo (relative to config)
      commit: "abc1234"            # pin to a specific commit
      setup_commands:              # optional: run inside the worktree before the agent starts
        - ["uv", "sync"]
```

::: warning 锁定 commit
对于打算随时间进行比较的评测，请始终显式设置 `commit`。如果省略 `commit`，micro-eval 会在运行时使用 `HEAD`——随着仓库演进，工作区会发生漂移，导致历史比较不可靠。
:::

## 隔离级别

`sandbox.level` 字段控制 agent 进程被约束的严格程度。各级别在 provider 协议（规格 §3.4.5）中定义。

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
configurations:
  - id: my-agent-v1
    agent:
      command: ["uv", "run", "my-agent"]
    sandbox:
      level: logical
```

### 级别 1 — `os_policy`

在 agent 进程周围添加 OS 级别的沙箱策略：

- **macOS**：Apple Seatbelt（`sandbox-exec`）将文件系统写入限制在工作区目录
- **Linux**：Bubblewrap（`bwrap`）创建具有私有文件系统视图的用户命名空间

此级别可防止 agent 意外（或故意）读取 `~/.ssh` 中的密钥、向工作区外的路径写入，或修改你的全局配置文件。

```yaml
configurations:
  - id: semi-trusted-agent
    agent:
      command: ["./external-agent"]
    sandbox:
      level: os_policy
      network: allowlist              # full | allowlist | none
      network_allowlist:
        - "api.openai.com"
        - "pypi.org"
    trust: semi_trusted
```

::: warning 降级至 logical
如果请求 `os_policy` 但宿主机上 Seatbelt 或 Bubblewrap 不可用（例如，未安装 `bwrap` 的 Linux），micro-eval 会**降级至 `logical`** 并在运行结果中记录一个 `mixed_isolation` 告警。运行不会中止，但该告警会在 UI 中显示，并在严格可比性检查中被排除。

若要求 `os_policy` 不发生静默降级，请设置 `sandbox.strict: true`。
:::

### 级别 4 — `vm`（远程执行）

在 E2B 或 Modal 提供的远程 VM 内运行 agent。这是最高隔离级别，适用于：

- 不受信任或对抗性的 agent
- 无论宿主 OS 如何都需要干净 Linux 环境的 agent
- 需要特定 OS 包或内核特性的任务

```yaml
configurations:
  - id: untrusted-agent
    agent:
      command: ["./unknown-agent"]
    sandbox:
      level: vm
      provider: e2b                   # e2b | modal
      template: "base-python-3.11"    # provider-specific template ID
    trust: untrusted
    network: none
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

## Provider 注册表

micro-eval 在运行时通过 `WorkspaceProvider` 协议和 provider 注册表选择合适的后端。你无需直接配置——注册表会检查 `sandbox.level` 字段和宿主环境来选择正确的后端。

| Provider | 级别 | 平台 |
|----------|-------|----------|
| `GitWorktreeProvider` | 0 — logical | 所有平台 |
| `SeatbeltProvider` | 1 — os_policy | macOS |
| `BubblewrapProvider` | 1 — os_policy | Linux |
| `E2BProvider` | 4 — vm | 任意（远程） |
| `ModalProvider` | 4 — vm | 任意（远程） |

## 信任级别

`trust` 字段传达意图，由 provider 注册表用于验证所选隔离级别是否合适。

| 信任级别 | 推荐隔离 | 典型用途 |
|-------------|----------------------|------------------|
| `trusted` | `logical` | 你自己的 agent、内部工具 |
| `semi_trusted` | `os_policy` | 你已审查过的第三方 agent |
| `untrusted` | `vm` | 下载的 agent、外部贡献者 |
| `adversarial` | `vm` | 红队测试、可能尝试逃逸的 agent |

::: warning 信任是建议性的，不是强制性的
设置 `trust: adversarial` 不会自动升级隔离级别。你还必须设置 `sandbox.level: vm`。信任用于文档、可比性元数据和未来的策略执行——本身不作为安全门控。
:::

## 网络策略

`sandbox.network` 字段控制 agent 进程的出站网络访问。它在级别 1 及以上生效。

| 策略 | 行为 |
|--------|----------|
| `full` | 无网络限制（级别 0 的默认值） |
| `allowlist` | 仅 `network_allowlist` 中列出的域名可达 |
| `none` | 阻止所有出站网络访问 |

```yaml{6-10}
configurations:
  - id: offline-agent
    agent:
      command: ["./my-agent"]
    sandbox:
      level: os_policy
      network: allowlist
      network_allowlist:
        - "api.anthropic.com"
        - "raw.githubusercontent.com"
    trust: semi_trusted
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
      timeout: 120
    sandbox:
      level: logical
    trust: trusted

tasks:
  - id: add-docstrings
    prompt: "Add Google-style docstrings to every public function in src/parser.py."
    workspace:
      type: git_repo
      repo: .
      commit: "a1b2c3d"
```

```yaml [os_policy — semi-trusted agent]
configurations:
  - id: external-agent
    agent:
      command: ["./bin/external-agent", "--mode", "edit"]
      input_mode: stdin
      timeout: 180
    sandbox:
      level: os_policy
      network: allowlist
      network_allowlist:
        - "api.openai.com"
    trust: semi_trusted

tasks:
  - id: implement-feature
    prompt: "Implement the feature described in SPEC.md."
    workspace:
      type: files
      sources:
        - path: SPEC.md
        - path: src/
        - path: tests/
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
      timeout: 300
    sandbox:
      level: vm
      provider: e2b
      template: "base-python-3.11"
      strict: true
    trust: adversarial
    network: none

tasks:
  - id: code-challenge
    prompt: "Solve the algorithmic problem in challenge.txt."
    workspace:
      type: files
      sources:
        - path: challenge.txt
    expectations:
      - type: contains
        value: "SOLVED"
```

:::

## 下一步

- [趋势分析](/zh/guide/trend-analysis) — 追踪评测结果随时间的变化，检测回归，并标注漂移断点
