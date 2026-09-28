# 安全模型

micro-eval 通过每个 cell 所选的工作区 provider 执行 agent 命令。本页说明信任模型、已有的保护措施，以及在运行不可信 agent 或任务之前需要了解的限制。

::: danger 运行前请仔细检查
默认的 `logical` 隔离会以你的用户账户在本机运行所配置的命令，命令能够访问该账户可访问的资源。在运行评测之前，请审查任务定义、workspace 类型和 agent 命令，尤其当任务提示词或 agent 二进制文件来自你不信任的来源时。选择更强隔离时，需要检查实际 provider 和 run caveat。
:::

---

## argv-Only 子进程执行

agent 和验证命令使用 **argv 列表**。本机 provider 和 Modal 直接执行该列表；E2B 在 SDK 边界进行 shell 引用序列化。任务提示词或 agent 输出中的 shell 元字符——反引号、分号、管道、`$()` 展开——保留为字面参数数据。显式配置的 shell 命令仍保留其正常 shell 语义。

**实际意义：** 即使提示词中包含 shell 注入尝试，以下任务定义也是安全的：

```yaml
# tasks/untrusted-prompt.yaml
id: injection-attempt
input_payload: "Summarize this: $(rm -rf /tmp/important)"  # 安全 — 不会被 shell 展开
workspace:
  type: blank

expectations:
  - type: exit_code
    value: 0
```

提示词文本会根据 agent 的 `input_mode`，以命令行参数或 stdin 的方式传递给 agent 进程，其内容不会触发 shell 展开。

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

密钥以全名注入子进程环境，agent 进程以标准环境变量的形式接收它们——例如，`MICRO_EVAL_SECRET_OPENAI_API_KEY` 可直接从环境中读取。

### 自动脱敏

micro-eval 在持久化前对捕获的文本进行声明 secret 值脱敏。Adapter 的 stdout、stderr 和文本 artifact 支持任意非空长度：整串匹配会精确替换为 `[REDACTED:NAME]`，子串重叠时优先替换较长的值。包含 NUL 字节的二进制 artifact 不进行文本脱敏，须单独处理。

脱敏后的输出示例：

```
Calling OpenAI API with key [REDACTED:MICRO_EVAL_SECRET_OPENAI_API_KEY]
```

不要在 `eval.yaml` 或任务文件中写入 secret。文本脱敏保护 run 结果和文本 artifact，但无法清理二进制字节，也无法撤回 agent 已发给外部服务的数据。

::: tip 哪些内容会被扫描
脱敏作用于：子进程 stdout、子进程 stderr、`file_exists` artifact 内容、`command` 期望的输出、LLM judge 的输入/输出，以及通过 UI 存储的任何人工标注文本。扫描基于值匹配——匹配的是实际密钥字符串，而非仅仅是键名。
:::

---

## Workspace 边界

每个评测单元（evaluation cell）在分配的 workspace 目录中运行，agent 进程的工作目录（`cwd`）设为该 cell workspace。本机 provider 使用项目下的目录；远程 provider 使用该 cell 的远程文件系统。

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
| `os_policy` | Seatbelt (macOS) / Bubblewrap (Linux) | 对 cell 命令实施 `full` 或 `none` | 宿主写入仅限当前 cell 工作区及其输出 staging 目录；可读宿主文件仍可访问 | 需要本机工具且已审查的 agent |
| `container` | Modal | 对远程沙箱实施 `full` 或 `none` | 每个 cell 一个远程容器 | 需要远程环境的 agent |
| `vm` | E2B | 对远程沙箱实施 `full` 或 `none` | 每个 cell 一个远程 VM | 需要远程环境的 agent |

在 task 的 `workspace` 块中配置隔离级别：

::: code-group

```yaml [Logical（默认）]
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: main
  isolation_level: logical
```

```yaml [OS Policy — macOS Seatbelt]
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: main
  isolation_level: os_policy
  network_policy: none
```

```yaml [Remote VM — E2B]
workspace:
  type: blank
  isolation_level: vm
  trust_level: untrusted
  network_policy: none
```

:::

单轮 setup、agent 执行和 command expectation 使用同一个 cell 执行上下文及所选 provider。OS 策略包装器作用于这三类命令；远程 provider 在同一个沙箱内运行它们。产物传输通过该 provider 的文件系统边界完成。多轮对话当前要求 `logical`；其他隔离级别会在工作区准备前被拒绝。

::: warning 仍需了解的边界
OS 策略隔离限制宿主写入，但不保护可读宿主文件中的秘密。超时和取消会向本机进程组发送 TERM，再发送 KILL；主动脱离该进程组的后代不在清理保证内。远程超时和取消会显式终止该 cell 的沙箱，清理失败会保留在结果中。离线 SDK contract 测试检查 API 调用，不能证明云服务的隔离或清理行为；live 验证需要 provider 凭据。
:::

OS 和远程 provider 会拒绝 `allowlist`，因为尚未实现明确的允许规则；不能将它理解为 `none` 或已经生效的域名过滤。`logical` 不强制执行网络策略。

### OS Policy 沙箱降级

如果配置了 `os_policy` 但平台不支持（例如 Seatbelt 不可用、Bubblewrap 未安装），micro-eval 会**降级为 `logical` 隔离**，并在 run 结果中添加一条附注：

```text
requested isolation os_policy unavailable on Linux; ran at logical
```

在将结果视为跨不同实际隔离级别的 run 可比之前，请检查 `run.json` 中的附注。OS provider 一旦选定，包装器启动、策略或命令失败会使 cell 失败，不会在沙箱外重试。

远程 provider（`e2b`、`modal`）**不会**降级——如果 provider 不可用或凭证缺失，run 会立即失败。请求的网络策略与实际生效的策略分别记录。远程 git observation 当前不可用，会记录为 caveat，不能作为已验证同起点的证据。

---

## 受保护测试的边界

`starter-tasks` 模板使用已安装的 `micro_eval.tools.verify_protected` 模块，在运行只读临时测试副本前后检查受保护 `tests/` 的 digest。验证器位于 agent 可写的 fixture 之外，因此修改 fixture 中的测试或新增测试文件会在这些检查中被拒绝。

被测模块与测试仍共享一个 Python 进程。导入时代码可以干扰测试运行器或其可访问的文件；digest 门禁不是对抗性隔离边界。通过表示受保护测试通过，且在检查时符合预期 digest。应保留工作区证据供复核，并选择合适的 workspace provider。

---

## Artifact 安全

从 agent run 收集的 artifact 在存储前经过多项安全检查：

**二进制检测** — 包含 NUL 字节的文件被标记为二进制。未超限的完整二进制 artifact 会保留，标记为 `redacted: false` 并记录 `binary_redaction_skipped` warning；不会渲染为文本或包含在文本摘要中。不能假定其中的字节已经脱敏。

**大小上限** — `guardrails.output_cap_bytes` 默认 **10 MiB**，限制每个捕获的 stdout/stderr 流及选中的输出；`guardrails.artifact_cap_bytes` 默认 **50 MiB**，限制产物持久化。超额产物正文会被省略；文本输出摘要可以保留经过脱敏的有界前缀。截断或省略会显式记录。

**分阶段写入** — provider 输出先进入临时接收目录，文本在该目录中脱敏，再仅将配置的 output mode 选中的产物导出到持久化 run 目录。未选中的原始文件不会发布为 run artifact。

**符号链接和硬链接保护** — 保留的 artifact 路径（例如，解析后会超出 run 目录的路径）在收集时会被拒绝。指向 artifact 边界外的符号链接不会被跟随。

**清单绑定访问** — UI 和报告生成器从不根据用户输入构造 artifact 路径。所有访问都通过 run 清单中的 `artifact_id` 查找进行，并在打开文件前检查解析路径是否在 run 目录内。

---

## 报告安全

HTML 报告使用**启用了自动转义**的模板引擎生成。嵌入报告中的 agent 输出、任务提示词和标注文本在渲染前均经过 HTML 转义。这可以防止报告在浏览器中打开时，因 agent 输出包含 HTML 或 JavaScript 而导致存储型 XSS。

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

## 团队服务器安全模型

使用 `micro-eval serve` 时，攻击面从"本地进程读取本地文件"扩展为"可通过网络访问的 HTTP 服务器"。服务器在**受信任的内网假设**下运行——所有团队成员均被信任，但网络路径仍需防御跨域攻击。

### CSRF 防护（4 层）

所有写操作 API 路由（`POST`/`PUT`/`PATCH`/`DELETE`）均强制执行：

1. **Content-Type** — 仅接受 `application/json`。拒绝 `form-urlencoded`、`multipart/form-data`、`text/plain`，从而阻断浏览器 `<form>` 和 `sendBeacon()` 的跨站提交。
2. **自定义请求头** — 必须包含 `X-Micro-Eval-Member`。浏览器在跨域简单请求中无法发送自定义请求头，除非经过 CORS 预检。
3. **不返回 CORS 头** — 服务器从不返回 `Access-Control-Allow-Origin`，因此来自其他源的预检请求会被浏览器拒绝。
4. **Host 头白名单** — 含有未知 `Host` 值的请求将被拒绝，以防止 DNS 重绑定攻击。

### 路径遍历防护

所有工作区和制品的访问均通过基于 ID 的查找与路径包含性校验进行：
- Workspace ID 必须匹配 `ws-<timestamp>-<hex>` 格式
- 解析后的路径必须保持在 `~/.micro-eval-server/workspaces/` 内
- 符号链接会被解析并再次检查路径包含性

### 配置覆盖白名单

enqueue 请求拒绝 `config_overrides`。应先编辑 workspace 配置，再预览生成的计划并提交。admission digest 将入队计划绑定到该次预览；配置或工作区输入发生变化后必须重新预览。

::: warning 仅限内网使用
团队服务器没有认证层。请勿将其暴露在公网上。`X-Micro-Eval-Member` 请求头是自报的，不经过验证——它提供的是归属标记，而非访问控制。
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
