# 安全模型

micro-eval 在你的本地机器上执行 agent 命令。本页说明信任模型、已有的保护措施，以及在运行不可信 agent 或任务之前需要了解的限制。

::: danger 运行前请仔细检查
micro-eval 会将你配置的命令作为子进程在你的机器上执行。一个会写文件、调用外部 API 或修改系统状态的 agent，将以你的用户账户身份执行这些操作。在运行评测之前，请务必审查任务定义、workspace 类型和 agent 命令——尤其当任务提示词或 agent 二进制文件来自你不信任的来源时。
:::

---

## argv-Only 子进程执行

micro-eval 中的每个 agent 命令和验证命令都以 **argv 列表**形式执行，而非 shell 字符串。

```python
# 内部实现，micro-eval 使用：
await asyncio.create_subprocess_exec(*argv, cwd=workspace_dir, env=cell_env)

# 而非：
subprocess.run(command_string, shell=True)  # 受信路径中从不使用
```

这意味着任务提示词或 agent 输出中的 shell 元字符——反引号、分号、管道、`$()` 展开——都会作为字面数据传递给进程，永远不会被 shell 解释。

**实际意义：** 即使提示词中包含 shell 注入尝试，以下任务定义也是安全的：

```yaml
# tasks/untrusted-prompt.yaml
id: injection-attempt
prompt: "Summarize this: $(rm -rf /tmp/important)"  # 安全 — 不会被 shell 展开
workspace:
  type: blank

expectations:
  - type: exit_code
    value: 0
```

提示词文本会根据 agent 的 `input_mode`，以命令行参数或 stdin 的方式传递给 agent 进程，shell 永远看不到它。

::: warning 旧式字符串命令
如果你以纯字符串而非列表的形式提供命令，micro-eval 会发出弃用警告，并通过迁移桥接用 `shlex.split` 拆分它。此代码路径不在受信路径中——请将所有命令迁移为列表形式：

```yaml
# 已弃用 — 请避免使用
command: "my-agent --model gpt-4"

# 正确做法
command: ["my-agent", "--model", "gpt-4"]
```
:::

---

## Secrets 通道

agent 所需的密钥必须通过专用通道传入——绝对不能硬编码在 `eval.yaml` 或任务文件中。

### 命名规范

所有密钥必须以 `MICRO_EVAL_SECRET_` 为前缀：

```bash
export MICRO_EVAL_SECRET_OPENAI_API_KEY="sk-..."
export MICRO_EVAL_SECRET_ANTHROPIC_API_KEY="sk-ant-..."
```

### 声明所需密钥

在 `eval.yaml` 中声明某个 configuration 需要哪些密钥。micro-eval 会在启动 run 之前验证所有已声明的密钥均存在于环境中：

```yaml{8-10}
configurations:
  - name: gpt-4o
    command: ["my-agent", "--model", "gpt-4o"]
    repetitions: 3
    environment:
      MODEL: "gpt-4o"
    required_secrets:
      - MICRO_EVAL_SECRET_OPENAI_API_KEY
```

密钥以全名注入子进程环境，agent 进程以环境变量的形式接收它们：

```python
# 在你的 agent 内部
import os
api_key = os.environ["MICRO_EVAL_SECRET_OPENAI_API_KEY"]
```

### 自动脱敏

micro-eval 会扫描所有捕获的文本——stdout、stderr、artifact 内容、evidence 文本以及人工标注评论——并在持久化到磁盘之前，将匹配已声明密钥的值替换为脱敏标记。

脱敏后的输出示例：

```
Calling OpenAI API with key [REDACTED:MICRO_EVAL_SECRET_OPENAI_API_KEY]
```

密钥**永远不会**被写入 `eval.yaml`、`run.json`、`result.json`、HTML 报告或任何其他 artifact。

::: tip 哪些内容会被扫描
脱敏作用于：子进程 stdout、子进程 stderr、`file_exists` artifact 内容、`command` 期望的输出、LLM judge 的输入/输出，以及通过 UI 存储的任何人工标注文本。扫描基于值匹配——匹配的是实际密钥字符串，而非仅仅是键名。
:::

---

## Workspace 边界

每个评测单元（evaluation cell）在一个独立的 workspace 目录中运行。agent 进程的工作目录（`cwd`）被设置为该 cell workspace，而非你的宿主项目根目录。

```
.micro-eval/
└── workspaces/
    └── r-20260615-001/
        └── hello__baseline__rep-1/   ← agent cwd
            └── (workspace 文件)
```

### 期望验证范围

`file_exists` 和 `command` 期望相对于 cell workspace 目录进行验证：

```yaml
expectations:
  - type: file_exists
    path: "output/report.txt"  # 相对于 workspace 目录解析，而非宿主根目录
  - type: command
    command: ["cat", "output/report.txt"]  # cwd = workspace 目录
```

试图逃逸 workspace 的路径（例如 `../../host-secret.txt`）会被拒绝，并报告边界违规错误。

### Artifact 访问

agent run 产生的 artifact 通过清单系统访问。每个 artifact 在收集时被分配一个 `artifact_id`，后续所有读取都经过边界检查，确保解析路径始终在 run 目录内：

```
artifact_id: "abc123"  →  .micro-eval/runs/{run_id}/artifacts/abc123/
```

API 或 UI 不会暴露对任意路径的直接文件系统访问。

### 源路径约束

当 workspace 从 `files` 或 `git_repo` 源初始化时，源路径被约束在项目根目录内。源路径中的路径遍历序列（`..`）会被拒绝：

```yaml
workspace:
  type: files
  source: "./fixtures/my-task"   # 合法 — 相对于项目根目录
  # source: "../../etc/passwd"   # 拒绝 — 路径遍历
```

---

## 隔离级别

micro-eval 支持四种 workspace 隔离级别，可按 configuration 选择。更强的隔离可降低 agent 损坏宿主系统或在 run 之间泄露数据的风险。

| 级别 | Provider | 网络隔离 | 文件系统隔离 | 适用场景 |
|---|---|---|---|---|
| `logical` | git worktree | 无 | 部分（仅 cwd） | 默认；你信任的开发/测试 agent |
| `os_policy` | Seatbelt (macOS) / Bubblewrap (Linux) | 可选（`network_policy: none`） | 是（沙箱 profile） | 在可信硬件上运行不可信 agent |
| `container` | Docker（未来） | 是 | 是 | CI 环境 |
| `vm` | E2B / Modal | 是 | 是 | 不可信 agent，生产环境评测 |

在 `eval.yaml` 中配置隔离级别：

::: code-group

```yaml [Logical（默认）]
configurations:
  - name: baseline
    command: ["my-agent"]
    workspace_provider: logical
```

```yaml [OS Policy — macOS Seatbelt]
configurations:
  - name: sandboxed
    command: ["my-agent"]
    workspace_provider: os_policy
    sandbox:
      network_policy: none   # 阻断出站网络
```

```yaml [Remote VM — E2B]
configurations:
  - name: remote
    command: ["my-agent"]
    workspace_provider: e2b
    required_secrets:
      - MICRO_EVAL_SECRET_E2B_API_KEY
```

:::

::: warning 本地运行器不提供网络隔离
默认的 `logical` 隔离级别**不**限制网络访问。在 `logical` 隔离下运行的 agent 可以发起任意出站网络请求、访问外部 API 或泄露数据。如果你在评测非自己编写的 agent，请使用 `os_policy` 并设置 `network_policy: none`，或使用远程 VM provider。完整的网络隔离需要 `os_policy`（部分）或 `vm`（完整）。
:::

### OS Policy 沙箱降级

如果配置了 `os_policy` 但平台不支持（例如 Seatbelt 不可用、Bubblewrap 未安装），micro-eval 会**降级为 `logical` 隔离**，并在 run 结果中添加一条附注：

```json
{
  "isolation_level": "logical",
  "isolation_caveat": "os_policy requested but Seatbelt/Bubblewrap unavailable; degraded to logical"
}
```

在将结果视为跨不同实际隔离级别的 run 可比之前，请检查 `run.json` 中的附注。

远程 VM provider（`e2b`、`modal`）**不会**降级——如果 provider 不可用或凭证缺失，run 会立即失败。

---

## Artifact 安全

从 agent run 收集的 artifact 在存储前经过多项安全检查：

**二进制检测** — 包含 NUL 字节的文件被标记为二进制。二进制 artifact 会被存储，但不会在 UI 中渲染为文本，也不会包含在报告摘要中。

**大小上限** — 子进程输出（stdout + stderr 合计）上限为 **10 MB**。单个 artifact 文件上限为 **50 MB**。超出限制的输出会被截断，并在末尾追加截断标记。

**符号链接和硬链接保护** — 保留的 artifact 路径（例如，解析后会超出 run 目录的路径）在收集时会被拒绝。指向 artifact 边界外的符号链接不会被跟随。

**清单绑定访问** — UI 和报告生成器从不根据用户输入构造 artifact 路径。所有访问都通过 run 清单中的 `artifact_id` 查找进行，并在打开文件前检查解析路径是否在 run 目录内。

---

## 报告安全

HTML 报告使用 Jinja2 生成，并**启用了自动转义**。嵌入报告中的 agent 输出、任务提示词和标注文本在渲染前均经过 HTML 转义。

```python
# 内部实现
env = jinja2.Environment(autoescape=True, loader=...)
```

这可以防止报告在浏览器中打开时，因 agent 输出包含 HTML 或 JavaScript 而导致存储型 XSS。

::: tip 自包含报告
HTML 报告内联嵌入所有数据，打开时不发起任何外部请求。共享或归档时无需暴露任何 `.micro-eval/` 内部内容，可以放心分享。
:::

---

## Web UI 网络边界

Web UI（`micro-eval ui`）运行一个本地 Next.js 服务器，直接从文件系统读取 `.micro-eval/` JSON 文件。它不会：

- 发起出站网络请求
- 将 API 路由暴露到网络（仅绑定到 `localhost`）
- 对用户进行身份验证（假定任何能访问该端口的人都是可信的）

::: warning 仅绑定本地地址
Web UI 绑定到 `127.0.0.1`，不建议在网络接口上对外暴露。未经添加自有认证层，请勿将其置于可被其他机器访问的反向代理后面。
:::

---

## 运行前安全检查清单

在评测来自外部来源的 agent 或任务之前，请使用以下检查清单：

- [ ] 所有 agent 命令均为列表形式（而非 shell 字符串）
- [ ] 所有密钥使用 `MICRO_EVAL_SECRET_*` 前缀，并在 `required_secrets` 中声明
- [ ] 任务 `source` 路径不包含 `..` 路径遍历序列
- [ ] Workspace 类型与任务相符（使用固定 commit 的 `git_repo` 以保证可复现性）
- [ ] 隔离级别与你的信任程度匹配（对不可信 agent 使用 `os_policy` 或 `vm`）
- [ ] 执行 agent 命令前，你已审查其具体行为
- [ ] 如果使用 `os_policy`，已确认沙箱实际生效（检查 `run.json` 中的附注）
- [ ] HTML 报告只在浏览器中打开来自你控制的 run 的内容
