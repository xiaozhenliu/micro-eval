---
id: LOCAL-COMPARATIVE-DECISION-01
title: 让单 baseline/candidate run 给出可审计的比较结论
effort: comparative-decision
type: task
status: ready
triage: ready-for-agent
executor: agent
blocked_by: []
created_at: 2026-08-29T17:40+08:00
updated_at: 2026-08-29T18:09+08:00
tags:
  - decision
  - activation
related:
  - docs/superpowers/specs/2026-06-02-mvp-profile.md
  - src/micro_eval/config/planner.py
  - src/micro_eval/decision/aggregation.py
  - src/micro_eval/decision/summary.py
  - src/micro_eval/models/configuration.py
  - src/micro_eval/models/decision.py
  - src/micro_eval/models/run.py
  - examples/multi-task-matrix/eval.mock.yaml
---

# LOCAL-COMPARATIVE-DECISION-01 — 让单 baseline/candidate run 给出可审计的比较结论

## What to build

为恰好包含一个 `baseline` 和一个 `candidate` 的完整 run 实现第一版保守比较闭环：从 run 自身持久化的不可变评测合同和 configuration role 出发，按 task 分组比较两侧二元验证结果，在证据、可比性、阈值和样本门槛均满足时输出 `improved`、`regressed` 或 `mixed`；条件不足时输出带有明确 caveat 的 `inconclusive`、`not_comparable` 或 `needs_human_review`。

本 ticket 只解决两配置的可信基础语义。它不通过 configuration 列表顺序猜测 role，不把全 run 的总通过率差直接当成比较理由，也不为了让 demo 好看而绕过 `EvaluationContract` 中的阈值和证据约束。

## Confirmed decisions

### 比较输入

- 只支持恰好一个 `role: baseline` 和一个 `role: candidate`。缺少 role、role 重复、出现第三个待比较 configuration，均不自动推断 winner。
- `RunPlan` 和 `RunRecord` 必须保存规划时的 configuration role 与完整 `EvaluationContract` 快照。report/recompute 只读取 run 内的快照，不重新读取可能已变化的 `eval.yaml`。
- 旧 run 和旧 decision artifact 缺少这些新增字段时仍须原样读取，并继续展示其中已经保存的 verdict。只有显式 recompute 且旧 `RunRecord` 缺少 role/合同快照时，才拒绝合成新 winner，返回带 `comparison_contract_unavailable` caveat 的 `inconclusive`；不得按 configuration 顺序补猜，也不得覆盖已有历史 decision artifact。
- 当前比较信号只包含 validator 产出的二元 pass/fail。只有 `required_evaluators` 仅要求 validator 时才允许自动强结论；合同要求 human、LLM judge 或其他 evaluator 时，在本 ticket 尚未定义跨 evaluator 合成规则，因此即使结果存在也返回带明确 caveat 的 `needs_human_review`，不能静默忽略它们。cost、latency 和非 validator 分数仍展示为事实，但不参与本 ticket 的 winner 判定。

### task 级判定

- 以 `task_id` 分组，分别计算 baseline 与 candidate 在该 task 上的 pass rate；repetition 不做 rep-1 对 rep-1 的一一配对。
- task 级 pass rate 严格遵循现有 `denominator_policy`。对于 `error`/`timeout` cell：`include_failed` 将其作为非 pass 计入分母，并附加 `execution_failure_counted` caveat；`exclude_failed` 将其排除。两种策略下都必须保留 cell、trace/artifact 或 evidence 引用，不能把执行失败悄悄折算成普通 validator fail。
- `decision_threshold` 在本 ticket 中表示 task 级 candidate pass-rate delta 的最小实质差异，合法范围为 `(0, 1]`：
  - `candidate_pass_rate - baseline_pass_rate >= decision_threshold`：该 task 为 `improved`；
  - `candidate_pass_rate - baseline_pass_rate <= -decision_threshold`：该 task 为 `regressed`；
  - 其余为 `unchanged`。
- `decision_threshold: null` 保持权威 MVP 规格中的原意：不自动判定 winner，输出带 `decision_threshold_not_set` caveat 的 `inconclusive`。
- 应用 `denominator_policy` 后，baseline 与 candidate 任一侧少于 `min_repetitions`、缺少可审计结果、run 尚未完成，或缺少合同要求的机器 evaluation/evidence，都不能把该 task 当成可判定样本。

### run 级合成

- 至少一个 task 为 `improved`、没有 task 为 `regressed`，其余均为 `unchanged`：run verdict 为 `improved`。
- 至少一个 task 为 `regressed`、没有 task 为 `improved`，其余均为 `unchanged`：run verdict 为 `regressed`。
- 同时存在 `improved` 与 `regressed` task：run verdict 为 `mixed`。
- 所有 task 均为 `unchanged`：run verdict 为 `inconclusive`，并说明差异未达到阈值。
- 任一 task 的比较输入不完整时不拼出强结论；根据下面的优先级返回受保护状态。
- `mixed` 在本 ticket 中仅表示 task 方向冲突，不表示“通过率更好但成本或耗时更差”。

### 保护状态与 confidence

判定按以下优先级执行，前一项命中后不得被后一项覆盖：

1. snapshot gate 不通过或两侧 task 集不一致：`not_comparable`；
2. 合同要求本 ticket 未支持自动合成的 evaluator（包括 human、LLM judge），或多个 evaluator 的结果存在冲突/尚无既定合成规则：`needs_human_review`；
3. role/合同不明确、run 不完整、所需机器 evaluation/evidence 缺失、低于 `min_repetitions`、阈值未声明或所有差异低于阈值：`inconclusive`；
4. 其余情况才允许产生 `improved`、`regressed` 或 `mixed`。

`repetitions < 3` 的 Basic Honest Stats 警告必须按每个 task/configuration group 计算，而不是按 configuration 的全部 cell 数计算。满足显式 `min_repetitions` 时，该警告不单独否决确定性比较；低于 `min_repetitions` 才是阻断条件。

本 ticket 产生的自动比较结论统一使用 `confidence: low`。这是对尚未校准统计不确定性的显式保守约束，而不是用“3 次 repetition”武断推导 `medium`。`medium`/`high` 的定义与推导整体延期；少于 3 次时仍额外携带 `low_sample` caveat。

每个非强结论至少有一条机器稳定、用户可读的 caveat；不再允许 `inconclusive`、`not_comparable` 或 `needs_human_review` 搭配空 caveats。

### 可审计输出

- `DecisionReport` 增加单个两配置 `comparison` 结构，而不是多 candidate 的 `comparisons[]`：记录 baseline/candidate configuration ID、使用的 threshold，以及每个 task 的两侧样本数、pass rate、delta、方向和支撑它的 cell/evaluation/evidence refs。
- run 级 `evaluation_refs` 和 `evidence_refs` 只引用本次判定实际检查过的事实，并与 task 级 refs 可追溯对应。
- `micro-eval report` 的 text、HTML 与 UI 对比页显示“candidate 相对 baseline”的 verdict、confidence、task 级理由和 caveats；不能只显示一个脱离主语的 `regressed`。
- 新字段保持向后兼容；Python model、JSON artifact、UI Zod schema 与 golden fixtures 同步更新。

## Acceptance criteria

- [ ] 规划和持久化层保存 configuration roles 与完整 `EvaluationContract` 快照；修改 `eval.yaml` 后重跑旧 report 不会改变旧 run 的比较语义。
- [ ] `decision_threshold` 的合法范围和 `null` 语义有配置校验及明确错误信息。
- [ ] decision 按 task 分组计算两侧 pass-rate delta，并严格遵循本 ticket 中的 run 级合成和保护状态优先级；实现不暗含 repetition 一一配对。
- [ ] `error`/`timeout` 在两种 `denominator_policy` 下按上述规则计入或排除，并保留 execution caveat 与事实引用。
- [ ] 低样本按 task/configuration group 判定；满足 `min_repetitions` 但少于 3 次时可产生 `improved`、`regressed` 或 `mixed`，同时 confidence 为 `low` 且带 `low_sample` caveat；本 ticket 的自动结论不产出 `medium`/`high`。
- [ ] `DecisionReport.comparison` 能从 verdict 追溯到 task、cell、evaluation 和 evidence；旧 decision artifact 仍原样读取并保留已有 verdict，只有缺少新输入的显式 recompute 才返回有理由的 `inconclusive`。
- [ ] text report、HTML report 和 UI 对相同 artifact 展示一致的主语、verdict、confidence、task 理由和 caveats。
- [ ] `examples/multi-task-matrix/eval.mock.yaml` 声明显式 `decision_threshold: 0.5`，与两次 repetition 下 pass rate 的最小变化单位一致；同时把错误的 “mixed” 预期修正为 `checker-beta` 相对 `checker-alpha` 的 `regressed (low)`：两个 task unchanged、一个 task regressed，并提示每侧每 task 只有 2 次 repetition。
- [ ] example README、相关中英文站点示例页和权威 MVP 设计文档同步精确判定规则与示例输出；实现该文档同步时使用仓库的 `micro-eval-site` skill。
- [ ] 实现完成后补齐 improved、regressed、mixed、全部 unchanged、阈值缺失、低于最小 repetition、Basic Honest Stats 低样本、snapshot mismatch、机器 evidence 缺失、human/多 evaluator 需要复核、role 不明确、partial run、两种 denominator policy 下的 error/timeout，以及旧 artifact 读取与 recompute 分流路径的测试。
- [ ] 至少有一条 subprocess 级 CLI 路径从离线 example 生成 report，并断言 `regressed (low)`、task 级理由和非空 caveats；Python、UI、example smoke 与站点验证全部通过。

## Deferred scope

- 多个 candidate 对同一 baseline 的 `comparisons[]`、run 级排序与 winner selection；两配置语义稳定后另开 ticket。
- cost/latency 与质量方向冲突的多指标 `mixed`。
- effect size、置信区间、显著性检验、随机性建模，以及 `medium`/`high` confidence 的语义与校准。
- 非二元 evaluator 分数的归一化与跨 evaluator 加权。
- `inconclusive_policy: block` 与 CLI/CI 退出状态的联动；本 ticket 只持久化该合同值，不改变 report 命令的进程退出语义。
- 跨 run 趋势和公开 benchmark 排名。

## Context

问题已由当前源码确认，仓库内 artifact 同时复现了用户可见症状，不是枚举预留造成的误报：

- `src/micro_eval/decision/summary.py` 从 `inconclusive` 起步，只会改写为 `not_comparable` 或 `needs_human_review`；它根本不读取 `decision_threshold` 或 role，因此即使配置显式阈值，`improved`、`regressed`、`mixed` 在当前构建路径中仍不可达。`confidence` 也是没有规则说明的固定 `low`。
- 当前 `RunRecord.configurations` 只保存 ID，configuration role 未持久化；除 `denominator_policy` 外，影响判定的 `EvaluationContract` 字段也未进入 run artifact，因此旧 run 无法仅凭自身重算可信结论。
- `examples/multi-task-matrix` 的现有 artifact 中，checker-alpha 为 6/6，checker-beta 为 4/6，snapshot gates、evaluation refs 和 evidence refs 都完整，当前源码重算得到 `inconclusive (low)` 且 caveats 为空。因为该配置当前是 `decision_threshold: null`，`inconclusive` 本身符合规格；这里真正暴露的症状是 caveat 为空，以及系统没有任何显式阈值可进入的比较分支。
- 该 example 不是 `mixed`：candidate 在两个 task 上持平，只在 `generate-report` 上退化，因此改为显式阈值 `0.5` 后应为 `regressed (low)`。
- 现有低样本逻辑按 configuration 的全部成功 cell 计数；三 task × 两 repetitions 被算成 6 个样本，从而漏掉“每个 task 只有两次”的警告。

这是 next release 的产品正确性和首次价值呈现阻塞项，但不是需要热修复的数据安全问题。先完成这个两配置闭环，再把它接入 DSH、benchmark walkthrough 或公开 demo，才能让传播入口兑现“从矩阵得到可解释结论”的承诺。
