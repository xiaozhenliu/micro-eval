---
title: DeepSeek Harness（DSH）接入可行性研究
doc_type: analysis
status: active
created_at: 2026-08-24T16:52+08:00
updated_at: 2026-08-24T16:52+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - agent-adapter
  - backlog
  - deepseek-harness
  - remote-execution
related:
  - docs/engineering/architecture-guardrails.md
  - docs/engineering/security-guidelines.md
  - docs/DEVELOPMENT.md
---

# DeepSeek Harness（DSH）接入可行性研究

## 文档定位

本文记录截至 2026-08-24 对 DeepSeek Harness（以下简称 DSH）与 micro-eval
集成方式的初步研究。它用于保留技术判断和未来讨论入口，**不是产品规格、架构
决策或 roadmap 承诺**。文中的 backlog 候选没有优先级、版本归属或交付日期；
在满足后文的实施触发条件前，不应据此开始开发。

本文关注如何把 DSH 作为被评测的 agent harness 接入 micro-eval。它不评价 DSH
本身的模型质量，也不提出现在替换 micro-eval 执行架构。

## 结论摘要

DSH 以 Web UI 作为主要用户入口，但它并非只能通过浏览器操作。官方代码和文档
同时提供了更适合自动化评测的接口：

- `headless` profile：接受一个一次性任务，在指定工作目录中运行 agent，完成后
  将最终 assistant 文本写到 stdout，并以退出码表达是否正常完成。
- ACP（Agent Client Protocol）：通过 stdio JSON-RPC 创建 session、提交 prompt、
  接收 assistant 更新、处理权限请求和取消执行。
- Web Host API：Web UI 使用的 HTTP API、事件流以及 workspace/session 能力。

因此，DSH 的 Web 形态不会破坏 micro-eval 的核心评测闭环。micro-eval 现有的
cell workspace、artifact、deterministic validation、judge、evidence 和 decision
模型都可以继续使用；需要扩展的是 agent 的调用 transport，而不是评测模型。

如果未来决定支持 DSH，推荐顺序是：先用 `headless` wrapper 验证用户路径，再以
ACP adapter 作为正式集成，只有在确实需要连接长期运行的远端 DSH Host 时才考虑
Web API adapter。浏览器 UI 自动化不应成为正式集成方案。

## 问题背景

micro-eval 当前最自然的评测对象是可由本地命令启动的 agent。每个 run cell 获得
独立 workspace，Execution Kernel 调用 AgentAdapter，并保存 stdout、stderr、
输出文件、验证结果和证据。DSH 的主要启动方式是：

```bash
npx @deepseek-ai/dsh web
```

这个命令启动本地 Node Host，并在默认情况下通过 `127.0.0.1:3080` 提供 Web UI。
从界面形态看，它不像典型 CLI/TUI agent，因此产生两个问题：

1. micro-eval 是否必须模拟人在浏览器中创建 session 和发送任务？
2. 如果 DSH Host 位于另一台服务器，micro-eval 的 cell workspace 和证据如何与
   远端执行对应？

第一个问题的答案是否定的；第二个问题则取决于 DSH 与 micro-eval 是否共享文件
系统，不能仅靠“增加一个 HTTP 请求”解决。

## DSH 的自动化接口

### Headless profile

DSH 官方 CLI reference 记录了 `headless` profile。典型调用形式为：

```bash
dsh --profile headless "run the tests"
```

一次调用会创建新的持久化 Agent，提交任务，等待 agent 静止，刷新 session，并从
该次 durable interval 中提取最后一条非空 assistant 文本。正常完成时文本写到
stdout；最终原因不是 `completed` 时退出码为非零。该 profile 不启动 HTTP Server
或浏览器前端。

这与 micro-eval 的单轮 subprocess 模型最接近，适合低成本验证 DSH 是否能在
cell workspace 内完成 coding-agent 任务。

当前 micro-eval 的任务输入只支持 stdin 或输入文件，而 DSH headless 接受位置
参数。短期验证可以使用一个薄 wrapper：从 stdin 或 `{input_file}` 读取任务，再
以独立 argv 参数调用 DSH。wrapper 不应拼接 shell 命令字符串。

### ACP

DSH 的 ACP package 是面向自动化客户端的 stdio JSON-RPC server，不是 UI
integration。其核心方法包括：

- `session/new`：以绝对 `cwd` 创建新 session；
- `session/prompt`：提交文本并等待 agent idle；
- `session/update`：发送已经提交的 assistant message；
- `session/cancel`：取消指定 agent；
- `session/request_permission`：把一次性权限请求交给客户端策略处理。

ACP 比 headless 更适合正式适配，因为它为 session 生命周期、取消和权限策略提供
了显式协议。它也比解析 Web API 更接近 micro-eval 的 agent transport 边界。

micro-eval 已有用于 conversational evaluation 的长驻 subprocess JSONL bridge，
但该 bridge 使用项目自定义的 `{turn, content}` 行协议，不能直接连接 ACP。未来
若实施，需要新增 ACP protocol bridge，而不是把 ACP 帧塞入现有协议。

### Web Host API

DSH Web Host 通过 `/api/<method>` 接收 JSON RPC 请求，并通过事件流向客户端推送
session 等状态。它能支持长期运行的 DSH server 和独立客户端，但集成成本更高：

- micro-eval 需要管理 Host 地址、健康检查、协议兼容和连接失败；
- session 完成判断依赖事件流，而不是单个同步 HTTP 响应；
- pending interaction、取消、恢复和冷 session 都需要显式处理；
- workspace 路径必须对 DSH Host 有意义；
- 默认 Web Server 没有 TLS、认证或完整的 origin policy，不应直接暴露到不可信
  网络。

Web API 因此只适合明确的远端或共享 Host 场景，不是首选的本地评测入口。

### 浏览器自动化

通过 Playwright 等工具操作 DSH Web UI 理论上可以完成任务，但不适合作为稳定的
评测 adapter：

- UI 结构和 selector 比协议更容易变化；
- 很难可靠区分“消息显示完成”和“agent 已经静止”；
- tool event、取消原因、权限交互和完整 session evidence 不易规范化；
- UI 故障会与 agent 能力故障混在同一结果中。

只有当目标系统完全没有 headless、协议或 API 接口时，浏览器自动化才应作为
探索性兜底，并在报告中把可比性降级。

## 与 micro-eval 当前架构的对应关系

micro-eval 已经具备以下可复用能力：

| micro-eval 能力 | 对 DSH 的意义 |
| --- | --- |
| 每 cell 独立 workspace | 可作为 DSH headless 或 ACP session 的 `cwd` |
| AgentAdapter 的规范化结果 | 可继续承载状态、输出、stderr、延迟和 failure mode |
| timeout 与输出上限 | 可约束 DSH 进程或协议调用 |
| artifact/evidence store | 可保存最终回复、session transcript 和适配器诊断 |
| deterministic validator | 不依赖 DSH UI，继续验证 workspace 结果 |
| conversational evaluation | 可复用评分路径，但需独立 ACP bridge |
| snapshot gate | 可判断参与比较的 cell 是否拥有相同起点 |

当前限制是 Execution Kernel 直接构造 `AgentAdapter`，而 `AgentAdapter` 又固定使用
`asyncio.create_subprocess_exec`。`AgentSpec` 只有 command、input/output mode、
timeout、env 和 secrets，没有 transport 类型或 transport-specific config。

这意味着现状不是“只能支持 TUI”，而是“只支持 subprocess invocation”。DSH
headless 可以包进这个边界；ACP 和 HTTP 则需要先把 adapter 选择从 Kernel 中解耦。
根据现有架构约束，Kernel 应只消费统一 adapter 契约，不应知道 DSH session 或
HTTP route 细节。

## 本地 Host 与远端 Host 的边界

### 同机执行

当 DSH 和 micro-eval 在同一台机器运行时，micro-eval 可以把已准备好的 cell
workspace 作为 DSH 的 `cwd`。执行完成后，现有 validator 直接检查同一个目录，
无需搬运文件。

仍需避免以下共享状态污染：

- 每个 cell 使用全新 session，不复用历史 conversation；
- 固定 DSH 版本、profile 和影响行为的配置；
- 记录 provider/model/permission policy 的有效选择；
- 评估共享 DSH home、持久化 session、缓存和全局插件是否影响重复实验；
- 并行 cell 不得共享可变 session 或交互请求。

### 远端执行

当 DSH Host 位于另一台服务器，micro-eval 创建的本地 workspace 路径对 Host 无效。
正式支持需要一个远程执行生命周期，而不只是一个 HTTP adapter：

1. 在远端创建隔离 workspace；
2. 上传 fixture，或在远端按固定 commit 构造 git workspace；
3. 创建绑定该绝对路径的 DSH session；
4. 提交任务、消费事件、处理权限策略和取消；
5. 下载最终回复、session log、文件变更和诊断信息；
6. 计算并保存远端环境与 workspace snapshot；
7. 清理远端 session/workspace，或明确记录保留策略。

该场景应与现有 remote provider / sandbox provider 的职责一起设计。否则本地
snapshot gate 可能显示“同起点”，实际 agent 却在不同远端环境中执行，形成错误
的可比性结论。

## 候选接入路径

### 路径一：Headless wrapper 验证

目的：用最小成本验证真实用户路径，不承诺正式支持。

候选工作：

- 提供仓库外或 example 内的安全 argv wrapper；
- 使用 `output_mode: stdout` 捕获最终回复；
- 用现有 files/git workspace 和 deterministic validator 跑少量 coding tasks；
- 记录固定 DSH 版本、profile、模型选择和实际命令；
- 验证 timeout、退出码、workspace 修改与重复运行的行为。

优点是无需修改核心 adapter。限制是只覆盖单轮任务，session trace 和权限交互证据
有限。

### 路径二：ACP adapter

目的：形成可维护的正式 DSH integration。

可能的架构变化：

- 为 AgentSpec 引入明确的 transport/provider 配置；
- 定义 transport-neutral adapter protocol；
- 由 adapter factory 或 registry 选择 subprocess / ACP adapter；
- 新增 ACP JSON-RPC client 与 session lifecycle；
- 把 committed assistant output、ACP diagnostics 和可获得的 session identifiers
  规范化为 AdapterResult、ArtifactRef、EvidenceItem 和 TraceRef；
- 对 permission request 使用显式、可记录的默认策略；
- timeout 时发送 `session/cancel`，随后执行有界进程终止。

正式设计时不应把 DSH 专有字段扩散到 Execution Kernel 或通用 RunRecord。

### 路径三：远端 Web/API adapter

目的：连接由用户或团队长期运行的 DSH Host。

该路径只有在存在明确远端部署需求时才值得设计。除协议客户端外，还必须定义：

- Host 信任、认证或安全隧道边界；
- workspace provisioner 与 artifact transfer；
- server/version capability negotiation；
- session ownership、清理和断线恢复；
- 并发配额与共享 Host 公平性；
- 远端 snapshot 与本地 decision evidence 的映射。

不应把“能向 `/api` 发请求”误认为已经具备可复现的远端评测能力。

## 风险与评测公平性要求

### 兼容性风险

DSH 当前处于 developer preview，官方明确提示会发生 breaking changes。任何验证
或正式集成都应固定精确 npm/package 版本，并把版本和 profile digest 写入 run
证据。实现前应重新核对当时版本的 headless、ACP 和 Web API 契约。

### Session 污染

复用已有 session 会把历史对话、工具结果或 compacted context 带进当前 cell，
破坏 same-start。每个 cell 必须创建新 session，并记录 session identity 与创建
策略。

### 配置漂移

DSH 的模型、工具、skills、插件、permission preset、sandbox 和 loop 都可组合。
只记录“DSH”或模型名不足以支持重放。至少需要记录影响 agent 行为的有效 profile、
插件集合、模型选择、权限策略和 DSH 版本。

### 权限与交互

无人值守评测不能无限等待人工批准或问答。adapter 必须定义可复现的权限处理策略，
例如只允许任务 workspace 内的预声明操作，并拒绝未知请求；每次自动决策应进入
evidence。安全实现还必须遵守项目的用户 run、服务和开发三层安全规范。

### 并发与共享资源

多个 cell 如果共享 Host、模型配额、插件全局状态或持久化目录，可能出现排队、
限流和状态竞争。报告应区分 agent latency 与 queue latency，并在无法证明隔离时
添加 comparability caveat。

## Backlog 候选

下面条目仅供未来 triage，不表示已接受或已排期。

### 候选 A：DSH headless feasibility spike

- 类型：研究 / prototype
- 目标：证明一个 DSH headless cell 能在 micro-eval workspace 中完成任务，并被
  现有 validator 和 artifact store 正确处理。
- 完成证据：固定版本的最小 example、至少一个成功和一个超时/失败路径、重复运行
  的 session 隔离说明。
- 非目标：正式 adapter API、远端 Host、Web UI automation。

### 候选 B：Transport-neutral AgentAdapter seam

- 类型：架构设计
- 目标：让 Kernel 通过统一契约选择 subprocess 或协议 adapter，同时保持当前
  subprocess 行为兼容。
- 完成证据：经评审的接口设计、failure taxonomy、lifecycle 与 artifact/evidence
  映射；不要求同时实现 DSH。
- 非目标：把每种 agent 的配置字段加入通用 RunRecord。

### 候选 C：DSH ACP adapter

- 类型：集成
- 前置：候选 A 证明用户价值，候选 B 已形成稳定 seam，DSH ACP 契约在目标版本中
  足够稳定。
- 目标：支持新 session、单轮或多轮 prompt、committed output、权限策略、取消、
  timeout 和协议诊断。
- 完成证据：隔离测试、真实 DSH smoke、失败路径、版本固定与 session evidence。
- 非目标：任意远端 server 和浏览器兼容。

### 候选 D：Remote DSH Host support

- 类型：远端执行能力
- 前置：存在明确用户需求，且已定义远端 workspace、安全和 artifact transfer
  边界。
- 目标：以可复现、可审计方式评测远端 DSH session。
- 完成证据：远端 same-start、断线/取消/清理、凭据处理、并发和证据回传测试。
- 非目标：直接暴露无认证的 DSH Web Server。

## 实施触发条件

只有至少满足以下条件之一，才建议把候选条目推进为设计或实现任务：

- 用户需要比较 DSH 与现有 CLI agent，并且无法通过一次性人工实验回答；
- 两个或以上真实 evaluation project 需要复用 DSH 接入；
- DSH 的 ACP 或其他自动化协议已稳定到可以固定兼容范围；
- 远端 DSH 是明确部署约束，而不是对 Web UI 形态的推测；
- 现有 subprocess wrapper 已暴露无法绕过的 session、trace 或交互限制。

在触发前，本研究文档本身就是交付物，不需要创建实现 issue、修改 schema 或加入
release scope。

## 非目标

- 不承诺某个 micro-eval 版本支持 DSH。
- 不为 DSH Web UI 开发专用浏览器机器人。
- 不因为单一 harness 改写 Kernel、RunRecord 或 evidence 模型。
- 不在本研究中定义最终 AgentAdapter API。
- 不假设本地 Web Host 等同于远端、多租户或安全服务。
- 不把 DSH session log 自动视为可信验证结果；deterministic validator 仍是独立
  证据来源。

## 参考资料

- [DeepSeek Harness 官方介绍](https://deepseek.com/harness/en/)
- [DeepSeek Harness GitHub 仓库](https://github.com/deepseek-ai/deepseek-harness)
- [DSH CLI profiles 与 headless reference](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/reference/README.md)
- [DSH ACP package reference](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/acp/acp/README.md)
- [DSH API Gateway 架构](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/api-gateway.md)
- [DSH HTTP Server 说明](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/web-server.md)
- [micro-eval 架构落地边界](../engineering/architecture-guardrails.md)
- [micro-eval 安全规范索引](../engineering/security-guidelines.md)
- [micro-eval 开发说明](../DEVELOPMENT.md)
