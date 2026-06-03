---
title: "决策记录：Rubric Engineering 与 micro-eval 评分系统的关系"
date: 2026-06-01
status: 已决策
type: decision-record
input: "2026-06-01-agentic-rubric-engineering.md"
affects: "2026-06-02-unicorn-design.md §4 评分系统"
tags:
  - decision-record
  - rubric-engineering
  - scoring
---

# 决策记录：Rubric Engineering 与 micro-eval 评分系统的关系

**日期**: 2026-06-01
**状态**: 已决策
**输入文档**: `2026-06-01-agentic-rubric-engineering.md`（研究报告）
**影响文档**: `2026-06-02-unicorn-design.md` §4 评分系统

---

## 背景

`agentic-rubric-engineering.md` 是一份基于学术文献的深度研究报告，提出了完整的
Verifier Protocol + VerifierEngine + 内置验证器目录 + 三层缓存 + 自适应路由的工程方案。

本文档记录：哪些采纳、哪些不采纳、为什么。

---

## 决策总结

| 报告内容 | 决策 | 理由 |
|---------|------|------|
| "确定性验证 > LLM 判断"原则 | ✅ 采纳 | 核心洞察，影响评分可信度 |
| 分层短路逻辑 | ✅ 采纳 | build 失败跳过后续，节省成本和时间 |
| 30% 成本约束规则 | ✅ 采纳 | 产品设计决策，防止验证比执行更贵 |
| 聚合策略（weighted_mean / min_critical） | ✅ 采纳 | 用户需要选择聚合方式 |
| 验证器只读访问 workspace | ✅ 采纳 | 安全原则，防止 agent 操纵评分 |
| "确定性失败不可被 LLM 覆盖" | ✅ 采纳 | 防止 prompt injection 翻转评分 |
| Verifier Protocol 接口 | ❌ 不采纳 | 与 DeepEval BaseMetric 重复 |
| VerifierEngine 调度层 | ❌ 不采纳 | 过度工程化，几十行代码足够 |
| 三层缓存架构 | ❌ 不采纳 | 过早优化，v1.0 不需要 |
| 自适应路由 | ❌ 不采纳 | 用户在 YAML 中声明跑哪些验证即可 |
| 内置 Verifier 目录（6 个） | ⚠️ 部分采纳 | 作为"内置验证能力"列表，不作为独立框架 |
| 实现路线图（Phase 1/2/3） | ❌ 不采纳 | 设计文档不含路线图 |
| 工期估算 | ❌ 不采纳 | 不属于设计文档范畴 |
| 安全威胁面（T1-T6） | ⚠️ 部分采纳 | T2（操纵评分管线）和 T6（Reward Hacking）补充到 §12 |

---

## 核心理由

### 为什么不建 Verifier Protocol？

报告中的 `Verifier Protocol` 本质上是在重新发明 DeepEval 的 `BaseMetric` 接口：

```python
# DeepEval 已有的
class BaseMetric:
    def measure(self, test_case: LLMTestCase) -> float: ...
    def is_successful(self) -> bool: ...
    @property
    def score(self) -> float: ...

# 报告提出的
class Verifier(Protocol):
    async def verify(self, ctx: VerifierContext) -> VerifierResult: ...
    def can_run(self, ctx: VerifierContext) -> bool: ...
```

区别仅在于：
1. Verifier 多了 `resource_limits`（沙箱隔离需求）
2. Verifier 的 context 是 workspace path 而非 LLM test case
3. Verifier 返回结构化 findings 而非单一 score

这些差异可以通过**在 DeepEval BaseMetric 之上封装一层薄适配器**解决，
不需要从零建一个独立的 Protocol + Engine + Registry。

### 为什么不建 VerifierEngine？

评分调度的核心逻辑是：

```python
# 这就是全部需要的"引擎"
async def run_scoring(task, workspace_path, config):
    # 1. 确定性验证（短路）
    for cmd in task.validation.commands:
        result = await subprocess_run(cmd, cwd=workspace_path)
        if result.returncode != 0:
            return Score(passed=False, reason=f"{cmd} failed")

    # 2. LLM 评判（如果配置了）
    if config.scoring.judge:
        llm_score = await deepeval_geval(task, workspace_path, config)

    # 3. 聚合
    return aggregate(deterministic_scores, llm_score, config.scoring.aggregation)
```

这不需要一个独立的 Engine 类、Plugin 注册机制、或 Protocol 定义。
它是 `engine/scorer.py` 中的一个函数。

### 为什么不建三层缓存？

v1.0 的典型使用场景：
- 10 个 task × 3 个 configuration × 3 次重复 = 90 次评分
- 每次评分：subprocess 调用（<10s）+ 可选 LLM 调用（<30s）
- 总时间：分钟级

缓存在这个规模下的收益极小，但引入的复杂度（cache key 计算、TTL 管理、
invalidation 策略）不成比例。当用户反馈"评分太慢"时再加。

### 与 DeepEval 的关系

```
micro-eval 评分层
├── Layer 0: 确定性验证
│   → subprocess 调用 pytest/npm test/cargo test
│   → 不需要任何框架，exit code 即结果
│
├── Layer 1: 启发式/规则验证
│   → diff 分析、schema 校验、lint 输出解析
│   → 简单 Python 代码，不需要框架
│
├── Layer 2: LLM-as-Judge
│   → 复用 DeepEval GEval（结构化 criteria + 评分）
│   → 或直接用 Anthropic SDK（GEval 本质是 prompt template）
│   → DeepEval 提供：多 metric 组合、评分一致性检查、pytest 集成
│
└── Layer 3: Pairwise / 人工
    → micro-eval 自建（DeepEval 不覆盖）
    → Pairwise comparison + Elo 排名
    → 人工标注 Web UI
```

DeepEval 的价值在于：
1. 不需要自己写 LLM judge prompt engineering
2. 提供 `GEval`（通用 LLM 评分）和 `FaithfulnessMetric` 等开箱即用的 metric
3. pytest 集成（`deepeval test run`）
4. 评分结果可视化（Confident AI 平台，可选）

DeepEval 不做的（micro-eval 需要自建）：
1. 确定性验证（subprocess 调用）
2. Pairwise comparison / Elo 排名
3. 校准式 Rubric（QQJ 模式）
4. 人工标注流
5. 跨 Configuration 矩阵对比

### 有没有现成的 Rubric Engineering 组件？

**没有一个 `pip install rubric-engine` 可以用。** 但各层都有现成工具：

| 层 | 现成组件 | 需要自建的 |
|----|---------|-----------|
| 测试运行 | pytest / npm test / cargo test | 自动检测逻辑 |
| 构建验证 | subprocess + exit code | 无 |
| Lint | ruff / eslint / clippy JSON output | 输出解析 |
| Diff 分析 | gitpython / unidiff | 规则匹配 |
| Schema | Pydantic / jsonschema | 无 |
| LLM Judge | **DeepEval GEval** | prompt 模板定制 |
| Pairwise/Elo | 无 | 完整实现 |
| 校准式 Rubric | 无（QQJ 论文阶段） | 完整实现 |
| 聚合/短路 | 无 | <100 行代码 |

---

## 对设计文档的具体修改

已在 `2026-06-02-unicorn-design.md` §4.1 中完成以下更新：

1. Layer 1 扩展为"确定性验证"，明确短路规则和不可覆盖原则
2. 补充内置验证能力列表（不作为独立框架）
3. Layer 2 明确复用 DeepEval GEval
4. 补充成本约束（30% 规则）
5. 补充聚合策略选项（weighted_mean / min_critical / dimension_aware）
6. 补充短路逻辑（build fail → skip all）

---

## 参考

- `docs/analysis/2026-06-01-agentic-rubric-engineering.md` — 完整研究报告
- [DeepEval GEval](https://github.com/confident-ai/deepeval) — LLM 评判层实现
- [Scale AI: Agentic Rubrics as Contextual Verifiers](https://arxiv.org/abs/2601.04171)
- [QQJ: Quantifying Qualitative Judgment](https://arxiv.org/abs/2605.17382)

---

## 覆盖核查与修订（2026-06-02）

> 本节核查本决策记录与 `2026-06-02-unicorn-design.md` 实际内容的一致性，并修正一处不准确陈述。

**§4.1 的 6 项更新已全部落实**（逐条核对设计文档 §4.1）：确定性验证层、内置验证能力列表、Layer 2 复用 DeepEval GEval、30% 成本约束、聚合策略、短路逻辑均已 present。其中"短路逻辑"在 2026-06-02 进一步演进为显式 `ScoreStage.should_run` + Aggregator 策略（设计文档 §4.1），比本记录写作时更彻底地落实了"不建独立 VerifierEngine"的决策——与本记录"❌ VerifierEngine 不采纳"一致。

**修正：安全威胁面（T1–T6）的落地描述不准确。** 本记录"决策总结"表称 *"T2（操纵评分管线）和 T6（Reward Hacking）补充到 §12"*，但实际情况是：

1. 设计文档 §12 使用**独立的 OWASP 编号体系（T1–T12）**，与本报告的 T1–T6 不是同一套编号。§12 的 T2 是"BYOK 密钥泄露"、T6 是"多租户隔离失败"，与本报告含义不同。
2. **"操纵评分管线"（本报告 T2）确实被采纳，但落在 §4.1**（"验证器以只读方式访问 workspace（防止 agent 操纵评分管线）"），不在 §12。
3. **"Reward Hacking / Goodhart's Law"（本报告 T6）并未进入设计文档任何章节**——全文检索无 `Reward Hacking`/`Goodhart`/`absence-based 标准`/`锚定任务（anchor task）`。即报告提出的缓解（absence-based 标准 + 定期换 rubric + 锚定任务）**尚未纳入**。

**未纳入 Reward Hacking 是否合理？** 合理，但应记为 deferred 而非"已补充"：
- 目标 Profile `mvp.local_pairwise.v1` 面向本地、可信、自己的 agent/skill；Reward Hacking 主要威胁出现在 **RL 训练闭环**或**长期对抗/不可信 agent 反复迭代**场景，小团队对比一次改动时风险低。
- 锚定任务、absence-based rubric 属于 [[2026-06-01-unicorn-vs-brd-research]] §4.8/§4.10 归类的"可信度增强/后置研究"，不阻塞最小决策闭环。
- 但设计文档应在 §15"不做"或 §8 Maturity 高 level 中**显式登记 Reward Hacking 防护为 deferred 能力**，避免本记录"已补充到 §12"的误导。

→ **更正后的结论**：上方"决策总结"该行应读为 ——「T2（操纵评分管线）已落在 §4.1；T6（Reward Hacking）评估为合理 deferred，待 `sandboxed_team.v1` / RL 场景再纳入」。
