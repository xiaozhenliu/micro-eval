# A2A 协议引入影响分析（修订版）

> **注意**：本文档为早期调研产物，最终设计决策已收敛到实施计划 `docs/superpowers/plans/2026-06-20-conversational-eval-plan.md`。provider 名称（如文中的 `a2a_agent`，最终为 `deepeval_conversational`）等技术细节以实施计划为准。

> 日期：2026-06-20（修订）
> 基于：micro-eval 执行层 + 评分层完整审查 + A2A v1.0 规范调研

---

## 0. 背景：要解决的真正问题

### 角色区分（关键）

| 角色 | micro-eval 对应 | AgentBeats 对应 |
|------|----------------|----------------|
| **被评测对象** | AgentSpec (subprocess command) | Purple Agent |
| **评测者 (Judge)** | DeepEvalJudgeClient (单轮 LLM 调用) | Green Agent |

### 当前评分链路

```
kernel._execute_cell()
  → adapter.invoke(agent, input)        # 执行层：单轮 subprocess
  → validate_cell(result)               # 确定性检查（exit_code, contains...）
  → evaluate_cell_with_judge(result)     # LLM judge：单轮 DeepEval GEval 调用
  → CellResult
```

**问题不在执行层，在评分层**：
- `JudgeClient.judge()` 是单轮接口（`llm_judge.py:29-36`），输入 prompt → 输出 score，无法多轮交互
- Judge 只看 agent 的最终输出做评分，不能像真实用户一样与 agent 多轮对话来检验其能力
- 缺少"Judge 扮演用户 → 与 agent 对话 → 基于完整对话评分"的能力

### 目标架构

```
kernel._execute_cell()
  → Judge Agent 发起首轮对话给 Evaluated Agent   # Judge 驱动对话
  → Evaluated Agent 响应
  → Judge Agent 追问（基于 task scenario / rubric） 
  → ... 多轮 A2A 交互 ...
  → Judge Agent 评分（基于完整会话 + rubric）
  → CellResult + 完整会话记录作为 evidence
```

Judge Agent = AgentBeats 的 Green Agent：既是**对话驱动者**（模拟用户场景），又是**评分者**（依据 rubric 判分）。

---

## 1. 影响面分析

### 1.1 执行层（engine/）— 影响有限

被评测 agent 的执行模型有两种情况：

**情况 A：被评测 agent 是 A2A server（已部署的远程 agent）**
- micro-eval 不需要 spawn subprocess
- Judge Agent 直接通过 A2A 与其对话
- 执行层不参与，只需新增"连接外部 A2A agent"的配置方式

**情况 B：被评测 agent 是 subprocess（现有模式）**
- Agent 需要保持存活以支持多轮
- micro-eval 做中间人：subprocess stdin/stdout ↔ A2A 消息转发
- `AgentAdapter` 需要扩展为多轮模式（进程保持存活，按行读写 JSONL）

**两种情况对现有执行层的影响**：

| 组件 | 情况 A | 情况 B |
|------|--------|--------|
| `AgentAdapter.invoke()` | 不使用 | 扩展为多轮循环 |
| WorkspaceProvider | 不使用（agent 自管理环境） | 不变（workspace 仍由 micro-eval 管理） |
| OS Sandbox | 不适用 | 不变 |
| Snapshot/Diff | 不适用 | 不变 |
| 超时管理 | 需要 per-turn + total timeout | 需要 per-turn + total timeout |

### 1.2 评分层（evaluation/）— 主要改动

当前评分层的两个组件：

**validator.py — 不变**
确定性验证（exit_code, contains, file_exists, command）保持不变，仍然在 agent 执行完毕后运行。

**llm_judge.py — 需要重大重构**

当前接口：
```python
# llm_judge.py:29-36
class JudgeClient(Protocol):
    name: str
    def judge(self, *, prompt: str, cell: RunCell, result: AdapterResult, config: JudgeConfig) -> JudgeOutcome:
        ...
```

问题：
1. `judge()` 是同步单轮调用，无法驱动多轮对话
2. 输入只有 `prompt`（拼接的文本），没有与 agent 交互的能力
3. 输出只有 `JudgeOutcome`（score + rationale），没有会话记录
4. Judge 被动地评分，不主动发起对话

需要的新接口（概念）：
```python
class ConversationalJudge(Protocol):
    name: str
    
    async def evaluate(
        self,
        *,
        cell: RunCell,
        agent_endpoint: AgentEndpoint,   # agent 的通信端点（A2A URL 或 subprocess handle）
        config: JudgeConfig,
        redactor: Redactor,
    ) -> ConversationalJudgeOutcome:
        """Judge 驱动多轮对话，然后评分。"""
        ...

@dataclass
class ConversationalJudgeOutcome:
    score: float | None
    pass_fail: str | None
    rationale: str
    scores: dict[str, float]
    conversation: list[Turn]       # 完整会话记录
    turn_count: int
    total_latency_s: float
```

### 1.3 配置层（models/configuration.py）

**JudgeConfig 需要扩展**：
```python
# 当前
class JudgeConfig(BaseModel):
    enabled: bool = False
    provider: Literal["deepeval"] = "deepeval"  # 只有 deepeval
    model: str = ""
    temperature: float = 0.0
    pass_threshold: float = 0.5

# 需要支持
class JudgeConfig(BaseModel):
    enabled: bool = False
    provider: Literal["deepeval", "a2a_agent"] = "deepeval"  # 新增 a2a_agent
    model: str = ""                  # deepeval 用
    agent_url: str | None = None     # a2a_agent 用：judge agent 的 A2A endpoint
    max_turns: int = 10              # a2a_agent 用：最大对话轮数
    turn_timeout_s: float = 60.0     # a2a_agent 用：单轮超时
    temperature: float = 0.0
    pass_threshold: float = 0.5
```

**AgentSpec 需要扩展**（支持被评测 agent 的 A2A 模式）：
```python
class AgentSpec(BaseModel):
    name: str
    command: list[str] = []          # subprocess 模式
    protocol: Literal["subprocess", "a2a"] = "subprocess"  # 新增
    url: str | None = None           # a2a 模式：agent 的 A2A endpoint
    interaction: Literal["single", "multi"] = "single"     # 新增
    input_mode: InputMode = InputMode.stdin
    output_mode: OutputMode = OutputMode.stdout
    timeout_s: float = 300.0
    max_turns: int = 1               # multi 模式的最大轮数
```

### 1.4 数据模型（models/）

**AdapterResult 需要扩展**：
```python
class AdapterResult(BaseModel):
    ...
    # 新增：多轮会话记录
    conversation: list[ConversationTurn] = []
    turn_count: int = 1

class ConversationTurn(BaseModel):
    turn: int
    role: Literal["judge", "agent"]
    content: str
    timestamp: str
    latency_s: float
```

**CellResult 需要扩展**：
```python
class CellResult(BaseModel):
    ...
    # 新增
    conversation_turns: int = 1
    conversation_ref: str | None = None  # artifact 引用
```

### 1.5 Kernel 编排层（engine/kernel.py）

`_execute_cell()` 的流程需要分支：

```python
# 当前流程（保留，用于单轮 + deepeval judge）
if judge_config.provider == "deepeval":
    adapter_result = await adapter.invoke(agent, input, cwd, ...)
    validation = await validate_cell(cell, adapter_result, ...)
    judge_result = evaluate_cell_with_judge(cell, adapter_result, ...)

# 新增流程（A2A judge 驱动多轮对话）
elif judge_config.provider == "a2a_agent":
    agent_endpoint = self._resolve_agent_endpoint(cell, workspace)
    judge_outcome = await conversational_judge.evaluate(
        cell=cell,
        agent_endpoint=agent_endpoint,
        config=judge_config,
        ...
    )
    # 会话记录作为 evidence 存档
    # validation 在会话结束后对最终输出运行
```

### 1.6 Trace 层（trace/）— 小改

ConversationTurn 数据自然成为 trace 的一部分：
```python
class ConversationalTraceProvider:
    def collect(self, cell, conversation, ...) -> TraceRef:
        return TraceRef(
            trace_id=...,
            provider="conversational",
            summary={
                "turn_count": len(conversation),
                "total_latency_s": sum(t.latency_s for t in conversation),
                ...
            },
        )
```

---

## 2. A2A 协议使用范围（修正版）

### 用到的 A2A 能力

| A2A 能力 | 用途 | 必须? |
|---------|------|-------|
| `a2a_sendMessage` | Judge → Agent 发消息；Agent → Judge 回复 | ✅ |
| Task 状态机 `input-required` | Agent 暂停等 Judge 追问 | ✅ |
| Message `parts` | 传递文本/文件/结构化数据 | ✅ |
| Task `history` | 自动记录完整会话 | ✅ |
| `a2a_getTask` | 查询 task 状态 | ⚠️ 轮询模式需要 |

### 不用的 A2A 能力

| A2A 能力 | 为什么不需要 |
|---------|------------|
| AgentCard 发现 | Judge 和 Agent 的 URL 在 eval.yaml 中配置 |
| SSE 流式 | 评测不需要实时流，轮询足够 |
| Push Notification | 本地/内网评测不需要 |
| 认证 (OAuth2/JWT) | 内网可信环境 |
| `a2a_listTasks` | micro-eval 自己管理 task 列表 |
| Agent 签名 | 不需要 |

### A2A 的角色

```
┌──────────────┐                    ┌──────────────────┐
│  micro-eval  │   orchestrate      │   Judge Agent    │
│  (kernel)    │ ──────────────►    │  (A2A client)    │
│              │                    │  LLM-powered     │
│              │                    │  drives convo    │
└──────────────┘                    └────────┬─────────┘
                                             │ A2A
                                             │ multi-turn
                                    ┌────────▼─────────┐
                                    │ Evaluated Agent   │
                                    │ (A2A server)      │
                                    │ or subprocess     │
                                    │ wrapped by        │
                                    │ micro-eval        │
                                    └──────────────────┘
```

micro-eval 是**编排者**：
1. 配置 Judge Agent 和 Evaluated Agent
2. 启动评测（告诉 Judge "用这个 task+rubric 去评测那个 agent"）
3. 收集结果（会话记录 + 评分）
4. 存储到 RunRecord

micro-eval **不直接参与 A2A 对话**——A2A 发生在 Judge ↔ Agent 之间。

---

## 3. 依赖策略（修正版）

### 方案 A：使用 a2a-sdk

```
pip install a2a-sdk           # Judge 作为 A2A client
pip install a2a-sdk[http-server]  # 如果需要包装 subprocess agent 为 A2A server
```

引入: protobuf, google-api-core, googleapis-common-protos, starlette, uvicorn
**过重**，不推荐。

### 方案 B：自写最小 A2A client + server（推荐）

**A2A Client（Judge 侧，~80 行）**：
- 只需 `httpx`（已间接依赖）
- 实现 `a2a_sendMessage` 的 JSON-RPC 调用
- 解析 Task 状态机

**A2A Server wrapper（被评测 agent 侧，~120 行）**：
- 用 `asyncio` 内置 HTTP server 或轻量 ASGI（不引入 starlette）
- 暴露 `a2a_sendMessage` endpoint
- 内部代理到 subprocess stdin/stdout
- 管理 Task 状态机

**总计 ~200 行 A2A 协议层，0 新依赖**（httpx 已有，asyncio HTTP server 是标准库）。

### 方案 C：httpx + 最小 Pydantic types

- A2A Message/Task/Part 的 Pydantic models（~60 行，复用现有 pydantic）
- httpx 做 JSON-RPC 调用（~40 行）
- asyncio.Protocol 做 subprocess ↔ A2A 桥接（~100 行）

**推荐此方案**：与 micro-eval 现有技术栈（pydantic + asyncio）一致，不引入新依赖。

---

## 4. 需要改动的文件清单（完整）

### 新增文件

| 文件 | 职责 | 预估行数 |
|------|------|---------|
| `src/micro_eval/a2a/types.py` | A2A Message, Task, Part 的 Pydantic models | ~60 |
| `src/micro_eval/a2a/client.py` | 最小 A2A JSON-RPC client（httpx） | ~80 |
| `src/micro_eval/a2a/server.py` | subprocess → A2A server wrapper | ~120 |
| `src/micro_eval/evaluation/conversational_judge.py` | 多轮对话 judge 实现 | ~200 |
| `src/micro_eval/trace/conversation_provider.py` | 会话 trace 采集 | ~40 |

### 改动文件

| 文件 | 改动内容 | 预估改动行数 |
|------|---------|------------|
| `models/configuration.py` | JudgeConfig + AgentSpec 新增字段 | ~30 |
| `models/run.py` | AdapterResult + CellResult 新增会话字段 | ~20 |
| `engine/kernel.py` | `_execute_cell` 新增 A2A judge 分支 | ~40 |
| `evaluation/llm_judge.py` | `resolve_judge_client` 支持新 provider | ~10 |
| `config/loader.py` | YAML 解析支持新字段 | ~5 |

### 不需要改动的文件

| 文件 | 原因 |
|------|------|
| `engine/adapter.py` | 单轮 subprocess 模式保持不变 |
| `engine/providers/` | WorkspaceProvider 协议不变 |
| `evaluation/validator.py` | 确定性验证不变 |
| `trace/langfuse_provider.py` | Langfuse 集成不变 |
| `trace/process_provider.py` | 进程 trace 不变 |
| `store/` | 存储层不变（Pydantic 向后兼容） |

**总计**：~500 行新代码 + ~105 行改动，0 新依赖。

---

## 5. 对现有功能的影响

### 完全不影响的

- ✅ 单轮 subprocess 评测（现有用户的 eval.yaml 不需要改）
- ✅ DeepEval GEval judge（保持为默认 provider）
- ✅ 确定性 validation
- ✅ Workspace 隔离 / OS Sandbox / Remote providers
- ✅ Snapshot / Diff / SameStartSnapshot
- ✅ Langfuse trace
- ✅ Decision 算法
- ✅ SQLite 索引 / 趋势分析
- ✅ Next.js Web UI（CellResult 新字段向后兼容）
- ✅ 455 个现有 pytest 测试

### 需要新增测试的

- A2A types serialization
- A2A client → server round-trip
- subprocess → A2A server wrapper
- ConversationalJudge 多轮评测流程
- Conversation trace 采集
- eval.yaml 新配置解析

### 安全考量

| 考量 | 处理 |
|------|------|
| Judge ↔ Agent A2A 通信中的 secrets | A2A Message.parts 经过 Redactor 处理 |
| subprocess wrapper 的端口暴露 | 绑定 localhost，评测结束即关闭 |
| Judge Agent 的 LLM API key | 通过 required_secrets 机制管理 |
| Agent 的 A2A URL | 限制为 localhost / 内网 CIDR |

---

## 6. 实施建议

### 分步实施

**Phase 1：A2A types + subprocess wrapper**（~180 行）
- 实现 A2A Message/Task/Part Pydantic models
- 实现 subprocess → A2A server wrapper
- 单独测试 wrapper 的多轮对话能力
- 不改任何现有代码

**Phase 2：ConversationalJudge + Kernel 集成**（~270 行）
- 实现 A2A client
- 实现 ConversationalJudge（LLM 驱动 + A2A 客户端）
- 扩展 JudgeConfig / AgentSpec
- Kernel 新增 A2A judge 分支
- 端到端测试

**Phase 3：UI 展示**（后续）
- Web UI 显示会话历史
- 对比页支持多轮会话对比

### 不建议

- ❌ 不使用 `a2a-sdk`（protobuf 生态太重）
- ❌ 不改现有 `JudgeClient` 接口（新建 `ConversationalJudge` 并行存在）
- ❌ 不强制所有 agent 支持 A2A（保持 subprocess 单轮为默认）
