---
title: "micro-eval UX 工程规范"
date: 2026-06-02
status: draft
type: engineering-guidelines
tags:
  - engineering
  - ux
  - micro-eval
---

# micro-eval UX 工程规范

micro-eval 是本地评测工作台，不是营销网站。UI 要帮助用户快速判断一次 agent / skill 改动是否值得推进。

## Product Feel

- 信息密度高，但不要混乱。
- 优先矩阵、表格、状态、证据链，而不是大面积装饰。
- 默认第一屏应该是可操作的 run / matrix / decision，不做 landing page。
- 视觉层级服务“比较、下钻、复盘”三个动作。

## Decision UX

用户必须一眼看到：

- 当前 verdict / DecisionStatus。
- 是否可比。
- 哪些 caveats 限制结论。
- baseline / candidate 或 configurations 的关键差异。
- pass rate、latency、cost-if-present。
- 哪些 task 造成 mixed / regressed / inconclusive。
- 证据链入口。

不允许：

- snapshot gate 失败时仍突出 winner。
- 把 low sample 当作普通成功。
- 用绿色/红色暗示没有证据支撑的结论。
- 把 raw stdout 当成评分解释。

## Result Matrix UX

MatrixHeatmap 是 MVP 的核心界面。

- 行：Task。
- 列：Configuration。
- cell：status、score/pass_fail、latency、cost-if-present、caveat marker。
- repetitions：可聚合显示，也可下钻到单次 rep。
- 失败 cell 必须标明失败类型：timeout、nonzero、crash、validation failed、not comparable。

## Artifact and Evidence UX

- ArtifactViewer 展示原始 stdout/stderr/diff/file。
- Evidence view 展示结构化摘要、来源、severity、关联 cell。
- DecisionSummary 从 evidence 下钻到 artifact，而不是反向让用户从 artifact 猜结论。
- secrets redaction 占位符应清晰可见，但不暴露原值。

## Forms and Controls

- 二元选项用 checkbox / toggle。
- 枚举选项用 select / segmented control。
- 数值参数用 input / slider / stepper。
- 工具按钮使用图标 + tooltip。
- 表格过滤与排序要可见、可撤销。
- 不用大段说明文字替代清晰状态和控件。

