# Scaling Managed Agents: Decoupling the Brain from the Hands

> Source: https://www.anthropic.com/engineering/managed-agents
> Published: Apr 08, 2026 — Anthropic Engineering Blog
> Authors: Lance Martin, Gabe Cemaj, Michael Cohen

## Introduction

AI Agent 的 harness 编码了对模型能力的假设，而这些假设随着模型进步会快速过时。Managed Agents 是 Anthropic 的托管服务，用于长时间运行的 agent 工作，围绕稳定的接口构建，即使底层 harness 变化也能持续工作。

之前的工程博客文章（building effective agents、designing harnesses）反复强调："harnesses encode assumptions about what Claude can't do on its own"——这些假设经常随着模型改进而过时。

举例：Claude Sonnet 4.5 展现出"context anxiety"（上下文焦虑），在接近上下文限制时会过早结束任务。团队在 harness 中加入了 context resets 来应对。然而，当同一 harness 在 Claude Opus 4.5 上运行时，这种行为已经消失了，使得 resets 变成了不必要的开销。

## Design Philosophy

团队从操作系统获得灵感。操作系统通过将硬件虚拟化为抽象（如 *process* 和 *file*）来解决"为尚未发明的程序设计"的问题——这些抽象足够通用，能适应尚不存在的软件。`read()` 命令无论是访问 1970 年代的磁盘组还是现代 SSD 都能工作。顶层抽象保持稳定，底层实现可以变化。

Managed Agents 遵循同样的模式，虚拟化 agent 的组件：

- **Session**：所有发生事件的 append-only 日志
- **Harness**：调用 Claude 并将 tool calls 路由到相关基础设施的循环
- **Sandbox**：Claude 可以运行代码和编辑文件的执行环境

每个组件的实现可以独立替换。系统"对这些接口的形状有主见，但对背后运行什么没有主见。"

## Don't Adopt a Pet

最初，所有 agent 组件住在一个容器里——session、harness 和 sandbox 共享一个环境。

但将所有东西耦合在一起创造了一个"宠物"（pets-vs-cattle 类比）："a named, hand-tended individual you can't afford to lose." 如果容器失败，session 就丢失了。

第二个问题：harness 假设 Claude 的工作在同一个容器中。当客户想将 Claude 连接到自己的 VPC 时，必须做网络 peering 或在自己环境中运行 Anthropic 的 harness。

## Decouple the Brain from the Hands

解决方案将"大脑"（Claude 及其 harness）与"双手"（sandbox 和 tools）和"session"（事件日志）分离。

### The harness leaves the container

Harness 不再住在容器内。它像调用任何其他 tool 一样调用容器：

```
execute(name, input) → string
```

容器变成了 cattle。如果它死了，harness 将故障作为 tool-call error 捕获并传递给 Claude。如果 Claude 决定重试，可以重新初始化一个新容器：

```
provision({resources})
```

### Recovering from harness failure

Harness 本身也变成了 cattle。Session log 存在于 harness 之外，恢复通过以下方式工作：

```
wake(sessionId)
getSession(id)        // returns the event log
emitEvent(id, event)  // writes durable events during the agent loop
```

一个新的 harness 可以重启，检索事件日志，并从最后一个事件恢复。

### The security boundary

在耦合设计中，Claude 生成的不受信任代码与凭证运行在同一个容器中。结构性修复确保 token 永远无法从 sandbox 中触及：

1. **Git**：Access token 用于在 sandbox 初始化时克隆仓库，并连接到本地 git remote。Push/pull 无需 agent 处理 token。
2. **Custom tools via MCP**：OAuth token 存储在安全 vault 中。Claude 通过专用代理调用 MCP tools，代理获取 session 关联 token，从 vault 获取凭证，再向外部服务发起调用。Harness 永远看不到凭证。

## The Session Is Not Claude's Context Window

长时间任务超出 Claude 的上下文窗口。Session 充当外部上下文对象，持久存储在 session log 中：

```
getEvents()
```

这允许 brain 通过选择事件流的位置切片来审查上下文——从上次停止的地方继续、回退到特定时刻、或重读特定操作前的上下文。

系统分离了可恢复的上下文存储（session）和任意的上下文管理（harness），因为未来模型可能需要不同的 context engineering。

## Many Brains, Many Hands

### Many brains

解耦后，容器仅在需要时通过 tool call 配置。推理在编排层拉取待处理事件后立即开始。结果：**p50 TTFT 下降约 60%，p95 下降超过 90%**。

### Many hands

将每个 brain 连接到 many hands，每个 hand 都是一个 tool：

```
execute(name, input) → string
```

一个 name 和 input 输入；返回一个 string。这个接口支持任何自定义 tool、任何 MCP server 和 Anthropic 自己的 tools。Harness 不知道 sandbox "is a container, a phone, or a Pokémon emulator."

## Conclusion

系统对 Claude 周围的接口有主见：Claude 需要操作状态（session）和执行计算（sandbox），需要扩展到 many brains 和 many hands。接口为长时间可靠、安全运行而设计，但"make no assumptions about the number or location of brains or hands that Claude will need."
