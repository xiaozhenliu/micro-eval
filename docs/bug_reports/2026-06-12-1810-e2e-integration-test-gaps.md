---
title: E2E 与集成测试缺口（Issue 清单）
doc_type: analysis
status: active
created_at: 2026-06-12T18:10+08:00
updated_at: 2026-06-12T18:10+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - review
  - test-coverage
  - e2e
  - integration
related:
  - docs/superpowers/specs/2026-06-02-test-architecture.md
  - docs/bug_reports/2026-06-12-1730-test-coverage-gaps.md
  - docs/superpowers/plans/2026-06-12-phase2-implementation-plan.md
---

# E2E 与集成测试缺口（Issue 清单）

## 背景

Phase 2 收口后的测试复盘第二部分（第一部分见
`2026-06-12-1730-test-coverage-gaps.md`，已修复）。现状底数：e2e 共 4 个文件
22 个用例，全部基于 Phase 1 执行链路；UI 侧 vitest 仅 3 个纯函数用例，
API route 零测试。以下按 issue 格式列出，全部确认需要做。

**前置事项**：开工前先在测试架构权威来源
`docs/superpowers/specs/2026-06-02-test-architecture.md` 登记新增的测试层级
（尤其 ISSUE-1 的 UI route 集成测试），spec 先行、实施在后（CLAUDE.md 硬规则）。

---

## ISSUE-1: UI API route 缺少跨语言契约集成测试

**严重度：P0（最高）**
**类型：集成测试缺失**

### 问题

`/api/runs/[id]` 与 Phase 2 新增的 `/api/runs/[id]/cells/[cellId]/trace`
直接消费 `.micro-eval/` 下 Python 写出的 JSON。这是 Pydantic（写端）与
zod（读端）之间唯一的跨语言契约边界，目前没有任何测试守护。Pydantic 加字段
而 zod 未同步时只能靠运行时报错发现——本次 denominator_policy 缺陷正是
双端漂移类问题。

### 验收标准

- 用 Python 侧真实产出的 run 目录作为共享 fixture（扩展现有
  `canonical-run-p0.json` 机制至 Phase 2 字段：decision.json、TraceRef、
  judge EvaluationResult）；
- vitest 中 route handler 读取该 fixture，响应通过 zod schema 严格解析；
- fixture 由 Python 测试套件生成或校验，确保两端消费同一份数据。

---

## ISSUE-2: 缺少 Phase 2 全开的「黄金路径」E2E

**严重度：P0**
**类型：E2E 缺失**

### 问题

现有 e2e 对 Phase 2 仅覆盖 process trace 持久化一个点。没有一条
「eval.yaml 启用 trace + judge（mock client）→ run → decision.json 落盘 →
`micro-eval report` 输出 pass@k 与 cost source」的组合验证。单元测试各自
全绿不等于管线串通正确（denominator_policy 缺陷即「每段都对、连起来断了」）。

### 验收标准

- 一个 repetitions≥3、双 configuration、trace + judge 同时启用的 e2e 用例；
- 断言：decision.json 存在且含 decision_report_id 与 per-configuration
  pass@k；TraceRef 持久化；judge EvaluationResult 不覆盖 deterministic
  失败结论；report 文本含 cost source 标注；
- judge 使用 mock client，无网络依赖。

---

## ISSUE-3: 旧版本 run 兼容性缺少固化 fixture

**严重度：P1**
**类型：回归保护缺失**

### 问题

Phase 2 计划的验收项「对 v0.1.x 旧 run 执行 report 不报错」没有对应的
固化用例，目前仅靠 `list_runs` legacy fallback 的单测兜底。下次 schema
演进时该承诺可能无声失效。

### 验收标准

- 一份真实 v0.1.x 格式的 `run.json`（decision 内嵌、无 decision.json）
  作为 fixture 提交进仓库；
- e2e 断言 `micro-eval report` 可消费且 verdict 来自 `run.json["decision"]`；
- UI zod schema 可解析同一 fixture（与 ISSUE-1 共享机制）。

---

## ISSUE-4: CLI 失败路径无契约测试

**严重度：P2**
**类型：E2E 缺失**

### 问题

dogfood CLI e2e 仅 1 个 happy path。坏配置、不存在的 run id、非 git 目录
等失败场景的退出码与报错文案没有任何契约，重构 CLI 时行为可能静默改变。

### 验收标准

- 2–3 个 subprocess 失败场景用例：非法 eval.yaml、`report --run 不存在的id`、
  非 git 仓库目录下发起 run；
- 断言非零退出码与关键报错文案；不追求 CLI 行覆盖率。

---

## ISSUE-5: Decision Surface 关键义务缺少组件级断言

**严重度：P2**
**类型：UI 测试缺失**

### 问题

Decision Surface 五条义务（Unicorn §5.8）中有两条是产品诚实性承诺，
目前仅靠手工走查：`not_comparable` / `inconclusive` 的 run 不得显示 winner；
低样本必须有 low_sample 警示。

### 验收标准

- 各一个轻量渲染断言（vitest）：not_comparable run 渲染复盘页/DecisionSummary
  不出现 winner 标记；low_sample caveat 在 UI 可见；
- 不做系统性组件快照测试（维护成本高于价值）。

---

## 实施顺序

ISSUE-1 → ISSUE-2 → ISSUE-3 → ISSUE-4 → ISSUE-5。
前两项（P0）应在 Phase 3 动工前完成：Phase 3 将再次改动执行链路
（Docker sandbox、复杂 workspace），届时这两道防线是回归的主要依靠。

## 明确不做（登记备查）

- 真实 Langfuse / DeepEval 联网集成测试（违反无网络依赖原则，SDK 漂移
  已由适配层 + fake client 单测收敛）；
- Docker / sandbox 集成测试（Phase 3 范围）；
- 系统性 UI 组件快照测试。
