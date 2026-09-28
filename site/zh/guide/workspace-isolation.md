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

本机 provider 在指定 ref 处创建隔离的 git worktree，agent 获得 git 历史记录并可以创建分支。远程 provider 先在本机准备该 ref，再上传其中的文件，排除 `.git` 和开发控制目录；远程 agent 不会获得仓库的 git 历史记录。

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
| 3 | `container` | Modal | 需要 SDK 与凭证 |
| 4 | `vm` | E2B | 需要 SDK 与凭证 |

### 级别 0 — `logical`

默认级别。agent 进程以你的完整用户权限运行，并以当前 cell 工作区作为工作目录。相对路径写入落在该工作区，但此级别不阻止访问其他宿主路径或网络。

适用于针对自己仓库运行的受信任 agent（你自己的代码）。

```yaml
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: main
  isolation_level: logical
```

### 级别 1 — `os_policy`

setup、单轮 agent 和 command validator 通过同一个 Seatbelt 或 Bubblewrap 执行上下文运行。宿主写入仅限当前 cell 工作区及独立的 cell 输出 staging 目录；不能写入 run 元数据或其他 cell 工作区。Seatbelt 允许广泛的宿主读取；Bubblewrap 暴露只读的运行时与项目根目录。两者都不承诺可读宿主文件的保密性。

```yaml
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: main
  isolation_level: os_policy
  trust_level: semi_trusted
  network_policy: none
```

::: warning 降级至 logical
如果请求 `os_policy` 但宿主机上 Seatbelt 或 Bubblewrap 不可用（例如，未安装 `bwrap` 的 Linux），micro-eval 会**降级至 `logical`**，并在 run caveat 中记录 provider 不可用及实际隔离级别。cell 的 snapshot gate 会带有告警，比较结果前需要检查该 caveat。
:::

OS provider 一旦选定，包装器启动、不支持的策略和执行失败都会使 cell 失败，不会在沙箱外重试。`full` 允许网络访问，`none` 拒绝网络访问；由于尚未实现明确规则，`allowlist` 会被拒绝。

### 级别 3 和 4 — 远程执行

`container` 选择 Modal，`vm` 选择 E2B。每个 cell 拥有一个远程沙箱，工作区准备、setup、单轮 agent 和 command validator 都复用该沙箱。工作区输入和输出产物通过 provider 的有界文件传输接口流转，不会把宿主本地路径当作远程路径。远程命令必须已安装在沙箱中，或随工作区一起提供。

安装 provider extra：`uv pip install 'micro-eval[e2b]'`、`uv pip install 'micro-eval[modal]'`，或安装 `uv pip install 'micro-eval[remote]'` 同时支持两者。受支持的 SDK 版本固定为 `e2b==2.31.0` 和 `modal==1.5.5`。

远程输入传输只接受常规文件，最多 4,096 个条目、总计 50 MiB。输出传输同时遵守配置的产物字节上限。链接、特殊文件、越界路径以及 `.git`、`.micro-eval` 等开发控制目录不会被传输。

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

已声明的 agent secret 会在捕获文本中脱敏。provider 控制凭据留在宿主环境中；远程命令拒绝这些凭据名和凭据值，即使它们被列入 agent 的 `required_secrets`。

远程网络策略默认为 `none`；`full` 和 `none` 在创建沙箱时生效，请求策略和实际生效策略分别记录。`allowlist` 会被拒绝。离线 SDK contract 测试验证受支持 SDK 接口的调用，不能证明 live 服务的隔离行为。带凭据的 live probe 为可选验证，必须单独报告。

远程沙箱生命周期为 3,600 秒，这是回收时限，不能作为显式清理成功的证据。无法确认创建或终止结果时，结果会记录分配或终止状态未知，不会声称成功。`tests/e2e/test_remote_provider_live.py` 中的带凭据检查需显式启用，默认跳过。

远程 git observation 当前不可用。结果会记录该限制，不会据此声称已验证同起点或 diff 为空。本机 agent 执行后的 observation 在 validator 之前采集，因此 validator 写入不会被记作 agent 改动。

超时终止远程沙箱后，无法再下载其中的输出产物；结果会记录该传输限制。

远程输出清单限制在 512 KiB 编码元数据内；其余条目会被省略并记录截断。无效控制响应若超出接收上限，会直接失败并触发沙箱清理。每个输出文件要么完整、原子地下载，要么被省略。

对于本机单轮命令，超时和取消会向进程组发送 TERM，再发送 KILL；主动脱离进程组的后代不在保证内。远程超时和取消会显式终止该 cell 的沙箱；正常完成也会清理，清理失败会被记录。

多轮对话当前仅支持 `logical`。cell 上下文创建所属 provider 的持久交互 bridge，与单轮命令执行分开。其他隔离级别不支持该 bridge，会在工作区准备前被拒绝。

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

workspace 上的 `network_policy` 字段作用于所选 OS 或远程 provider 内的 setup、单轮 agent 和 command validator。`logical` 不强制执行网络限制。OS provider 不可用时可能降级至 `logical`，因此需要检查实际隔离级别和 caveat。

| 策略 | 行为 |
|--------|----------|
| `full` | provider 允许网络访问；OS 策略的默认值 |
| `allowlist` | OS 和远程 provider 拒绝；尚未实现明确规则 |
| `none` | Seatbelt 拒绝网络操作；Bubblewrap 创建独立网络命名空间；远程 provider 禁止出站访问。远程 provider 的默认值。 |

```yaml{6-10}
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: main
  isolation_level: os_policy
  trust_level: semi_trusted
  network_policy: none
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
  network_policy: none
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
