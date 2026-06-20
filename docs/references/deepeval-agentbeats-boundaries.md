# DeepEval 接口边界 × AgentBeats 架构抽象：事实调研

> 日期：2026-06-20
> 来源：DeepEval 官方文档/源码 + AgentBeats 多个 Green Agent 实际源码
> **实际验证版本**：deepeval 4.0.5（`uv run --extra judge` 环境，2026-06-20 验证）

---

## 1. DeepEval 的真实边界

### 1.1 本质：纯 Python 库，不是服务

- `pip install deepeval`，所有评估逻辑在本地 Python 进程内执行
- **没有** HTTP API / REST API / gRPC / WebSocket 端点
- **没有** server 模式、daemon 模式
- **没有** A2A 支持
- **没有** MCP server 模式（只能评估 MCP agent，自身不是 MCP server）
- **没有** webhook / event / callback 机制
- **没有** YAML/JSON 配置驱动模式

外部系统调用 DeepEval 的唯一方式：
1. `import deepeval` 在 Python 进程中直接调用
2. `deepeval test run test_file.py` CLI 命令（本质是 pytest runner）
3. Confident AI REST API `POST /v1/evaluate`（付费 SaaS，评估在他们服务器跑）
4. 社区项目 `deepeval-api`（FastAPI 封装，非官方）

### 1.2 programmatic 接口

```python
from deepeval import evaluate
from deepeval.test_case import ConversationalTestCase, Turn
from deepeval.metrics import ConversationCompletenessMetric

# 输入：Python 对象
test_case = ConversationalTestCase(
    turns=[Turn(role="user", content="..."), Turn(role="assistant", content="...")],
    scenario="...",
    expected_outcome="...",
)

# 同步调用，阻塞直到完成
result: EvaluationResult = evaluate(
    test_cases=[test_case],
    metrics=[ConversationCompletenessMetric(threshold=0.7)],
)

# 输出：结构化 Python 对象
for tr in result.test_results:
    print(tr.success, tr.metrics_data)
```

返回类型：
```python
class EvaluationResult(BaseModel):
    test_results: List[TestResult]
    confident_link: Optional[str]
    test_run_id: Optional[str]

@dataclass
class TestResult:
    name: str
    success: bool
    metrics_data: List[MetricData]
    conversational: bool
    input: Optional[str]
    actual_output: Optional[str]
    turns: Optional[List[TurnApi]]
    ...
```

### 1.3 ConversationSimulator

> **注意：实际 import 路径与官方文档不一致。** 官方文档示例写 `from deepeval import ConversationSimulator`，但 deepeval 4.0.5 中该类实际位于 `deepeval.simulator` 子模块。顶层 `deepeval` 命名空间不导出 `ConversationSimulator`。已在 2026-06-20 通过 `uv run --extra judge` 环境实际验证。

```python
from deepeval.test_case import ConversationalTestCase, Turn
from deepeval.dataset import ConversationalGolden   # 注意：不在 test_case 模块
from deepeval.simulator import ConversationSimulator # 注意：不在 deepeval 顶层

# model_callback 三种签名重载
async def callback(input: str) -> Turn: ...
async def callback(input: str, turns: List[Turn]) -> Turn: ...
async def callback(input: str, turns: List[Turn], thread_id: str) -> Turn: ...

simulator = ConversationSimulator(
    model_callback=callback,        # 必选：包装被评测 agent
    simulator_model="gpt-4o",       # 可选：驱动模拟用户的 LLM
    async_mode=True,                # 可选：并发（默认 True）
    max_concurrent=5,               # 可选：并发上限（默认 5，非官方文档中的 100）
    language="English",             # 可选：模拟用户语言
)

goldens = [ConversationalGolden(
    scenario="...",                  # 必选：会话场景描述
    expected_outcome="...",          # 可选：期望结果（默认 None）
    user_description="...",          # 可选：模拟用户描述（默认 None）
    # 其他可选字段（4.0.5 验证）：context, name, additional_metadata,
    # comments, custom_column_key_values, turns, multimodal, images_mapping
)]

# 返回 List[ConversationalTestCase]
test_cases = simulator.simulate(
    conversational_goldens=goldens,
    max_user_simulations=10,
)
```

**model_callback 内部可以做任何事**（包括 HTTP 调用远程 agent），DeepEval 只关心返回值 `Turn`。

> **4.0.5 验证的两个关键行为陷阱：**
> 1. **参数名必须是 `input`**（不是 `user_input`）。DeepEval 内部用 `inspect.signature` 检查 callback 的参数名，然后以 `**kwargs` 形式传入 `{"input": ..., "turns": ..., "thread_id": ...}` 中匹配的子集。参数名不对会导致 callback 收到空参数。
> 2. **`simulate()` 和 `evaluate()` 内部调用 `loop.run_until_complete()`**。如果在已运行的 asyncio event loop 中直接调用，会抛出 `RuntimeError: This event loop is already running`。解决方案：用 `run_in_executor(None, fn)` 在独立线程中运行。注意：如果 model_callback 内部需要 asyncio I/O（如 subprocess 通信），callback 必须是**同步**函数，通过 `asyncio.run_coroutine_threadsafe(coro, main_loop).result()` 把 I/O 调度回主循环——因为 asyncio subprocess 流绑定创建它们的事件循环。

### 1.4 Confident AI REST API（付费 SaaS）

```bash
POST https://api.confident-ai.com/v1/evaluate
Header: CONFIDENT_API_KEY: <key>
Body: { "metricCollection": "...", "llmTestCases": [...] }
→ { "success": true, "data": { "id": "TEST-RUN-ID" } }

POST https://api.confident-ai.com/v1/simulate/conversation
# 云端模拟对话
```

其他端点：Metrics CRUD、Datasets、Test Runs、Traces、Spans、Prompts、Annotations。

### 1.5 多轮评估指标（完整列表）

| 指标 | 类别 | 评测维度 |
|------|------|---------|
| ConversationCompletenessMetric | 对话质量 | 用户意图满足率 |
| TurnRelevancyMetric | 对话质量 | 每轮响应相关性 |
| KnowledgeRetentionMetric | 对话质量 | 跨轮知识保持 |
| RoleAdherenceMetric | 行为合规 | 角色一致性 |
| TopicAdherenceMetric | 行为合规 | 话题边界 |
| GoalAccuracyMetric | Agentic | 目标达成 |
| ToolUseMetric | Agentic | 工具使用质量 |
| MultiTurnMCPUseMetric | Agentic | MCP primitive 使用效率 |
| TurnFaithfulnessMetric | RAG | 响应忠实度 |
| TurnContextualRelevancyMetric | RAG | 检索相关性 |
| TurnContextualPrecisionMetric | RAG | 检索精度 |
| TurnContextualRecallMetric | RAG | 检索召回 |
| ConversationalGEval | 自定义 | 自然语言定义的任意标准 |
| ConversationalDAGMetric | 自定义 | DAG 决策树评估 |

---

## 2. AgentBeats 的实际架构

### 2.1 分层（从代码中提取的事实）

```
A2A 协议层 (a2a-sdk)
  ├── 纯传输：HTTP + JSON-RPC + SSE
  ├── 类型：Message, Task, Artifact, Part (TextPart/DataPart/FilePart)
  ├── 服务端：AgentExecutor 接口, A2AStarletteApplication
  ├── 客户端：A2AClient
  └── 不包含任何评估概念

AgentBeats 平台层 (agentbeats SDK)
  ├── Purple Agent 封装：BeatsAgent (wraps OpenAI Agents SDK)
  ├── 平台集成：battle context, launcher, Supabase backend
  ├── 场景管理：agentbeats-run CLI
  └── 不包含评估框架

评估逻辑层 (每个 Green Agent 自定义)
  ├── 完全是 application-level 代码
  ├── 每个 Green Agent 用不同的工具
  └── 没有统一的评估框架
```

### 2.2 Green Agent 实际用了什么评估工具

从源码中提取的事实（不是推测）：

| Green Agent | 评估工具 | 评分方式 |
|-------------|---------|---------|
| Tau2 (Sierra) | `tau2-bench` 库 | `evaluate_simulation()` → 二进制 pass/fail |
| Terminal-bench | 自写 `Verifier` | Docker 跑测试脚本 → pass/fail |
| Debate Judge | `google-genai` Gemini SDK | LLM-as-judge → 4 维度浮点分 |
| BFCL/ComplexFuncBench | 自写比对逻辑 | 函数调用准确率 |
| **没有任何 Green Agent 使用 DeepEval** | — | — |

### 2.3 Green Agent 内部架构（从代码中提取）

所有 Green Agent 的公共模式：

```python
# 1. 实现 a2a-sdk 的 AgentExecutor 接口
class Executor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue):
        msg = context.message
        task = context.current_task
        updater = TaskUpdater(event_queue, task.id, context_id)
        agent = Agent()
        await agent.run(msg, updater)

# 2. Agent.run() 是真正的评估逻辑
class Agent:
    async def run(self, message: Message, updater: TaskUpdater):
        # 解析评测请求
        request = EvalRequest.model_validate_json(get_message_text(message))
        participants = request.participants  # {"agent": "http://purple:8000"}
        config = request.config              # {"domain": "airline", "num_tasks": 3}
        
        # 用 Messenger 与 Purple Agent 多轮对话
        messenger = Messenger()
        response = await messenger.talk_to_agent(
            agent_url=participants["agent"],
            message="请完成任务...",
        )
        
        # 用领域特定工具评分（不是 DeepEval）
        score = domain_specific_evaluate(response)
        
        # 通过 A2A Artifact 返回结果
        await updater.add_artifact(
            parts=[
                Part(root=TextPart(text=f"Score: {score}")),
                Part(root=DataPart(data={"score": score, "pass_rate": ...})),
            ],
            name="Result",
        )

# 3. Messenger 封装 A2A 客户端
class Messenger:
    async def talk_to_agent(self, agent_url, message, new_conversation=True):
        client = A2AClient(url=agent_url)
        msg = Message(parts=[Part(root=TextPart(text=message))], role="user")
        if not new_conversation:
            msg.context_id = self.context_ids[agent_url]  # 多轮复用 context
        response = await client.send_message(msg)
        return get_message_text(response.result)
```

### 2.4 A2A 在 AgentBeats 中的使用位置

```
agentbeats-run CLI
  │
  │ A2A (发 EvalRequest)
  ▼
Green Agent (A2A server)
  │
  │ A2A (多轮对话)
  ▼
Purple Agent (A2A server)
```

**A2A 只用于 agent 间通信**。Green Agent 调用评估工具时（tau2-bench、Gemini SDK 等），是直接 Python import，不通过 A2A。

---

## 3. 关键事实总结

| 问题 | 事实 |
|------|------|
| DeepEval 能被 A2A 调用吗？ | 不能。它是纯 Python 库，没有 HTTP 端点。需要自行封装。 |
| AgentBeats 的 Green Agent 用 DeepEval 吗？ | 不用。没有任何 Green Agent 使用 DeepEval。 |
| Green Agent 用 A2A 调评估工具吗？ | 不用。评估工具通过 Python import 直接调用。 |
| A2A 在 AgentBeats 中用在哪？ | 只在 agent ↔ agent 之间（CLI→Green、Green→Purple）。 |
| DeepEval 有远程 API 吗？ | Confident AI 有 REST API（付费 SaaS）。DeepEval 开源版没有。 |
| 有人把 DeepEval 封装成 A2A 服务吗？ | 没有。社区有 FastAPI 封装（deepeval-api），但不是 A2A。 |
| ConversationSimulator 能连远程 agent 吗？ | 可以。model_callback 是 async 函数，内部可做任何事包括 HTTP 调用。 |
