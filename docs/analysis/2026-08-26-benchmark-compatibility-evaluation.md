---
title: micro-eval Benchmark 兼容性与阶段性适配评估
doc_type: analysis
status: active
created_at: 2026-08-26T12:27+08:00
updated_at: 2026-08-26T12:27+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - agent-eval
  - benchmark
  - compatibility
  - conformance
  - roadmap
related:
  - micro-eval-brd.md
  - docs/superpowers/specs/2026-06-02-unicorn-design.md
  - docs/engineering/architecture-guardrails.md
  - docs/engineering/security-guidelines.md
---

# micro-eval Benchmark 兼容性与阶段性适配评估

## 文档定位

本文评估业界 benchmark 的运行机制与 micro-eval 当前执行、评测和决策模型的兼容性，
并记录现阶段的范围决策。目标读者是 micro-eval 维护者及未来编写 Benchmark Adapter
的贡献者。

本文是一份决策支持材料，不是产品规格或交付承诺。它不包含 benchmark 下载和运行
教程，也不规定具体版本排期。具体实现仍需单独规格、验收标准和开发计划。

## 结论摘要

现阶段应只适配与 micro-eval 当前功能一致的 **终态可验证型 benchmark**：

- 每个任务相互独立；
- 任务输入在执行前确定；
- 初始环境可以表示为 blank、files 或 Git workspace；
- 被评测对象可以作为一个 CLI Agent 进程运行；
- Agent 自己完成内部推理和工具调用，benchmark 不需要逐步接管 action；
- 最终 stdout、文件、代码变更或 workspace 状态足以判定结果；
- evaluator 可以在 Agent 结束后确定性执行；
- 当前采用二元结果和 pass@1／简单成功率，不引入新的聚合语义。

据此，建议采用两级近期验证对象：

1. **机制验证：HumanEval pass@1**。它可以低成本验证任务导入、输出捕获、官方测试、
   per-task 证据与 pass@1 聚合是否闭环，但不能充分代表完整 coding Agent 产品价值。
2. **产品验证：SWE-bench Verified 单 prediction／resolved rate**。它的 issue → Git
   workspace → CLI coding Agent → patch → 官方测试 → resolved/unresolved 流程最接近
   micro-eval 的目标对象。接入必须委托 SWE-bench 官方 evaluator，不能自行重写
   resolved 判定。

MBPP pass@1 与 HumanEval 属于近似机制，可以在首个 Adapter 稳定后补充，不应同时建设
两套重复接入。Terminal-Bench／Harbor、完整 lm-eval、τ-bench、OSWorld、WebArena 和
隐藏测试 benchmark 暂不进入当前原生适配范围。

## 1. 评估问题

本报告区分三个容易混淆的问题：

1. **能否启动**：是否能通过一个 wrapper 或 shell command 启动 benchmark。
2. **是否自然适配**：benchmark 的任务、执行和评分语义能否由当前模型无损表达。
3. **是否可对照权威结果**：micro-eval 接入是否保留了上游版本、环境、evaluator、指标
   和聚合规则，并有一致性证据。

“能否启动”不是适配标准。理论上任何 harness 都可以作为子进程启动，但如果所有任务
语义、交互和评分都隐藏在一个不透明 wrapper 中，micro-eval 只看到退出码，就没有形成
可复用的评测能力，也无法证明结果与权威 benchmark 可比。

## 2. micro-eval 当前能力画像

当前稳定执行模型可以概括为：

```text
TaskSpec(input_payload + workspace + expectations)
  -> RunPlan(Tasks x Configurations x Repetitions)
  -> AgentAdapter(one CLI process)
  -> stdout / file / directory / workspace result
  -> deterministic validator
  -> EvaluationResult
  -> binary aggregation and DecisionReport
```

关键事实如下：

- `TaskSpec` 提供静态 `input_payload`、rubric、expectations 和本地 workspace 声明；参见
  [`models/task.py`](../../src/micro_eval/models/task.py)。
- `AgentSpec` 使用 argv command，输入为 stdin 或 file，输出为 stdout、file 或 directory；
  参见 [`models/configuration.py`](../../src/micro_eval/models/configuration.py)。
- deterministic validator 当前支持 `exit_code`、`contains`、`file_exists` 和 `command`；
  参见 [`evaluation/validator.py`](../../src/micro_eval/evaluation/validator.py)。
- `EvaluationResult` 已能保存一个主 score 和多个命名 score，但默认 deterministic validator
  仍产出二元 0/1；参见 [`models/evaluation.py`](../../src/micro_eval/models/evaluation.py)。
- 当前聚合以 configuration 为单位汇总二元 pass rate、pass@k、pass^k、延迟和成本；参见
  [`decision/aggregation.py`](../../src/micro_eval/decision/aggregation.py)。
- Artifact／Evidence／Trace 与 Decision 分层是正确基础：Decision 只能读取 Evaluation 和
  Evidence，不能直接解释裸 stdout；参见
  [`architecture-guardrails.md`](../engineering/architecture-guardrails.md)。

因此，当前产品不是通用 benchmark runner，而是一个面向完整 CLI Agent／Skill、使用本地
workspace 和事后 verifier 的比较与决策工具。这与
[`micro-eval-brd.md`](../../micro-eval-brd.md) 对评测对象的定义一致。

## 3. 当前阶段的自然适配资格门槛

一个 benchmark 只有在以下问题全部回答“是”时，才进入当前适配范围：

| 维度 | 资格问题 | 不满足时的判断 |
|---|---|---|
| Task | 每个样本能否无损映射为一个独立 TaskSpec？ | 需要新的任务／session 模型 |
| Input | Agent 所需输入是否在运行前确定？ | 需要 benchmark 驱动的交互循环 |
| Environment | 初始状态是否可表示为本地文件或 Git workspace？ | 需要新的 Environment Adapter 或上游 harness |
| Agent | 是否能由一个 CLI 进程完成整个任务？ | 需要 session／remote protocol Adapter |
| Observation | 是否只需检查最终输出和终态？ | 需要 action／observation event 模型 |
| Evaluator | 是否可在任务结束后确定性运行？ | 需要在线 simulator 或隐藏 evaluator |
| Metric | 当前是否只需二元 per-task 结果和 pass@1／简单均值？ | 需要 benchmark-native aggregation |
| Authority | 是否有公开、可固定版本的上游 evaluator？ | 只能标记为非官方或导入远端结果 |

Adapter 可以翻译文件格式、字段名称和命令调用，但不得改变 prompt、环境、正确性定义、
denominator 或聚合规则。若必须重新解释这些语义，则该 benchmark 不属于当前自然适配范围。

## 4. Benchmark 兼容性矩阵

| Benchmark／机制 | Task 适配 | 执行适配 | 评分适配 | 当前判断 |
|---|---:|---:|---:|---|
| HumanEval pass@1 | 高 | 高，需薄输出 wrapper | 高，官方测试为确定性二元结果 | 近期机制验证候选 |
| MBPP pass@1 | 高 | 高，需薄输出 wrapper | 高，机制与 HumanEval 近似 | HumanEval 稳定后再补充 |
| SWE-bench Verified 单 prediction／resolved rate | 高 | 高，issue + Git workspace + CLI Agent | 中高，必须调用官方 Docker evaluator | 近期产品验证候选 |
| Terminal-Bench／Harbor | 高 | 中，环境由 per-task container/harness 掌握 | 中，verifier/reward 协议不同 | 暂缓，等待 harness/environment Adapter |
| lm-eval `generate_until` + exact match 子集 | 中 | 中，评测对象通常是模型而非完整 Agent | 中，prompt/filter 配置必须由上游掌握 | 非当前优先级 |
| lm-eval log-likelihood／perplexity | 低 | 低，当前 Agent Interface 不暴露 token likelihood | 低，指标与聚合不同 | 不进入 Agent 原生范围 |
| τ-bench | 低 | 低，simulator 逐轮执行 tool action 并更新 DB | 低，官方 reward 依赖环境终态与沟通结果 | 未来交互评测路线 |
| OSWorld／WebArena | 低 | 低，需要 GUI/browser observation-action loop | 低，依赖环境状态与专用 evaluator | 未来交互评测路线 |
| 隐藏测试／托管 leaderboard | 视任务而定 | 视任务而定 | 本地不可用 | 仅支持 submission export/result import |

### 4.1 HumanEval 的作用边界

HumanEval 的公开流程是“prompt → 代码 completion → 执行测试 → functional correctness”。
在 pass@1 模式下，它接近当前一任务、一输出、一次确定性验证和一个二元结果的模型。
官方实现见 [openai/human-eval](https://github.com/openai/human-eval)。

它适合验证以下机制：

- benchmark task ID 和版本能否进入 run identity；
- Agent 输出能否被规范化为官方 completion；
- 官方测试输出能否形成 artifact 和 evidence；
- micro-eval per-task 结果是否与官方 evaluator 一致；
- pass@1 是否能从相同 denominator 得到相同结果。

它不适合作为 micro-eval 产品价值的唯一证明，因为它主要测代码 completion，而 micro-eval
的核心对象是能够在 workspace 中工作数分钟并产生复杂文件变更的完整 Agent。

### 4.2 SWE-bench Verified 的作用边界

SWE-bench 官方 evaluator 接收 `instance_id`、`model_name_or_path` 和 `model_patch`，在
Docker 环境中应用 patch 并运行测试，产出 per-instance report、测试输出和
resolved/unresolved 分类。官方流程见
[SWE-bench Evaluation Guide](https://github.com/SWE-bench/SWE-bench/blob/main/docs/guides/evaluation.md)。

它与 micro-eval 的目标路径高度一致：

```text
issue input
  -> 固定 repo/base commit workspace
  -> CLI coding Agent 修改代码
  -> 捕获 patch
  -> SWE-bench 官方 evaluator
  -> report/test output/patch evidence
  -> resolved rate
```

近期接入应只支持每实例单 prediction，并保留官方 resolved rate 指标及以下限制：

- micro-eval 负责 Agent configuration、运行矩阵、证据链和比较；
- 上游 SWE-bench harness 负责 patch 应用、Docker 测试和 resolved 判定；
- 不实现自定义“近似 SWE-bench”测试；
- 不在首个版本中宣称 pass@k、多 split、云端 evaluator 或排行榜提交能力；
- 任何实例缺失、环境失败、patch 无法应用和测试失败都保留上游原始分类。

## 5. 当前阶段的建议顺序

### 阶段 A：建立最小 Benchmark Conformance 闭环

以 HumanEval pass@1 为机制验证对象，目标不是追求模型分数，而是证明：

1. 上游 task identity 能固定进入 micro-eval run；
2. 同一份冻结 completion 在上游 evaluator 和 micro-eval 接入路径中得到逐任务一致结果；
3. 官方测试日志、输入、输出和版本信息进入 Evidence Chain；
4. infrastructure error 与 functional failure 不混淆；
5. 聚合结果使用相同 task 集合和 denominator。

### 阶段 B：建立与产品定位一致的权威锚点

以 SWE-bench Verified 单 prediction／resolved rate 为首个 Agent benchmark，验证完整 CLI
coding Agent、Git workspace、代码变更、官方 scorer 和 configuration 比较能否形成闭环。

阶段 B 不依赖阶段 A 的具体 Adapter 实现，但依赖阶段 A 明确的 conformance 元数据、证据
和逐任务对照方法。两者应共享 benchmark identity、native result 和 conformance report
模型，避免每个 benchmark 自行发明结果格式。

### 阶段 C：只扩展相同机制，不扩张执行模型

阶段 A/B 稳定后，可以增加 MBPP pass@1 或其他满足资格门槛的静态确定性 benchmark。
当前阶段不因为“候选数量更多”而引入 interactive driver、GUI environment、模型
log-likelihood Interface 或隐藏 evaluator 工作流。

## 6. Adapter 验收标准

每个被标记为可对照权威结果的 Adapter 必须满足：

1. **版本固定**：记录上游仓库、commit/release、dataset split、task IDs 和必要 digest。
2. **输入一致**：记录 Agent 实际看到的 prompt、workspace 起点、资源、timeout 和网络策略。
3. **官方评分**：直接委托上游 evaluator，或提供与上游逐任务一致的 parity 证据。
4. **原生指标保留**：先保存 benchmark 原生字段和指标，再映射到通用 EvaluationResult。
5. **失败分类保留**：Agent failure、verifier failure、infrastructure failure 和 missing result
   不得合并为一个普通 fail。
6. **证据完整**：原始 prediction/patch、官方 report、测试输出、日志、命令和版本均可追溯。
7. **聚合一致**：task grouping、repetition、denominator、micro/macro aggregation 与上游一致。
8. **标签诚实**：未完成一致性验证时只能标记为 `compatible-unverified`，不能声称结果可与
   官方排行榜直接比较。

Harbor 对 Adapter parity 的定义可作为参考：相同 Agent、模型、prompt 和配置下，原始
benchmark 与适配版本应测量同一数量，分数在统计上不可区分，并保留 parity experiment
记录。参见 [Harbor Adapter Guide](https://www.harborframework.com/docs/datasets/adapters)。

## 7. 当前实现前置风险

在开始 workspace 型 benchmark Adapter 前，需要先处理一个现有执行生命周期风险：

- 当前 Kernel 在普通 cell 路径中先 cleanup prepared workspace，随后才把
  `prepared.path` 传入 deterministic validator；参见
  [`engine/kernel.py`](../../src/micro_eval/engine/kernel.py) 中 cleanup 与 `validate_cell`
  的调用顺序。
- `file_exists` 和 `command` expectation 默认检查 Agent workspace，因此 Git worktree 被删除后，
  文件终态和测试命令可能无法可靠验证。

这是当前功能路径的正确性问题，不是 benchmark 新能力。SWE-bench-like workspace Adapter
不得绕过该问题；应先保证“Agent 运行 → validator／artifact 捕获 → cleanup”的生命周期
顺序正确并有集成验证。

另外，虽然 `WorkspaceSpec` 可以声明 container isolation，当前 Interface 不能直接表达和
构建 benchmark 提供的每任务 Dockerfile/image。因此 Terminal-Bench／Harbor 不能仅凭
`isolation_level: container` 被认定为当前自然适配。

## 8. 过程评估与未来 benchmark 对齐

完整设计已经包含 TraceProvider、file-based trajectory import、event log 和
`trajectory_grading`。这条路线可以在未来支持 coding trajectory、τ-bench、OSWorld 等
过程型 benchmark，但不能把“事后读取 trace”误认为“已经能驱动交互环境”。

未来对齐至少需要：

- 完整、有序、可版本化的 trajectory/event artifact；
- 能委托上游 simulator 或控制 observation-action loop 的 Trial Driver；
- benchmark-native evaluator 与 micro-eval process evaluator 分离；
- environment reset、state snapshot、timeout、取消和恢复语义；
- 官方 metric 与 micro-eval 诊断 metric 的命名空间隔离。

例如：

```yaml
scores:
  benchmark.tau2.reward: 1.0
  benchmark.tau2.db_reward: 1.0
  micro_eval.trajectory.tool_efficiency: 0.82
```

`benchmark.*` 用于对照权威结果，`micro_eval.*` 用于解释过程质量。micro-eval 的过程分数
不得覆盖或修改官方 benchmark 主指标。

该路线暂不进入当前实施范围。建议只有在以下条件同时满足时启动：

1. 至少一个当前型 Adapter 已完成 conformance 验证；
2. 出现明确用户需求，且目标 benchmark 具有稳定、可自动化的官方 harness；
3. 当前 Evidence／Trace 模型已能保存完整 trajectory，而不只是摘要或外部 URL；
4. Execution Kernel 已形成可替换 trial execution mode 的稳定 Seam；
5. 团队接受相应环境依赖、运行成本和复现责任。

## 9. 范围决策

截至 2026-08-26，采用以下决策：

- micro-eval 不建设或维护自己的公共 benchmark suite；继续把 benchmark 视为外部、可固定
  版本的评测资产和 evaluator。
- 当前阶段只适配终态可验证型 benchmark，不扩张为通用交互式 benchmark framework。
- 以 HumanEval pass@1 验证最小接入机制，以 SWE-bench Verified 单 prediction／resolved
  rate 验证 Agent 产品价值。
- 官方结果优先；micro-eval 负责运行矩阵、证据链、比较和决策，不重新定义 benchmark
  正确性。
- 过程评估保留为未来路线，用于在官方结果之外增加轨迹质量和根因分析；在触发条件满足前
  不开始实现通用 Trial Driver。

## 10. 参考资料

### 项目内资料

- [micro-eval BRD](../../micro-eval-brd.md)
- [Unicorn Design](../superpowers/specs/2026-06-02-unicorn-design.md)
- [MVP Profile](../superpowers/specs/2026-06-02-mvp-profile.md)
- [Architecture Guardrails](../engineering/architecture-guardrails.md)
- [安全规范索引](../engineering/security-guidelines.md)
- [Pier vs Unicorn 分析](2026-06-02-pier-vs-unicorn-analysis.md)

### 上游资料

- [OpenAI HumanEval](https://github.com/openai/human-eval)
- [SWE-bench Evaluation Guide](https://github.com/SWE-bench/SWE-bench/blob/main/docs/guides/evaluation.md)
- [Harbor Tasks](https://www.harborframework.com/docs/tasks)
- [Harbor Adapter Parity Guide](https://www.harborframework.com/docs/datasets/adapters)
- [EleutherAI lm-evaluation-harness Task Guide](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/docs/task_guide.md)
- [τ²-bench Evaluation](https://github.com/sierra-research/tau2-bench/blob/main/docs/evaluation.md)
- [OSWorld](https://github.com/xlang-ai/OSWorld)
