---
title: "micro-eval 前端工程规范"
date: 2026-06-02
status: draft
type: engineering-guidelines
tags:
  - engineering
  - frontend
  - nextjs
  - micro-eval
---

# micro-eval 前端工程规范

适用范围：`ui/`。

## Stack

- Next.js 16。
- React 19。
- TypeScript strict mode。
- Zod v4。
- Tailwind CSS v4。

## Data Access

- UI 不直接信任文件系统 JSON。
- 所有 run / cell / artifact / evaluation 数据经过 zod parse。
- API Route / Server Component 通过统一数据访问层读取项目数据。
- 项目根目录从配置或环境变量注入，不在组件内硬编码。
- 组件只消费 typed data，不接触 raw filesystem paths，artifact viewer 除外。

## Component Boundaries

建议组件按产品对象组织：

- RunList
- ResultMatrix
- CellDetail
- ArtifactViewer
- EvaluationPanel
- DecisionSummary
- CaveatBanner

组件不要重新计算业务结论。业务结论来自 Decision data。组件只负责展示、过滤、排序、下钻和人工输入。

## UI State

- 人工评分必须持久化到后端数据文件，不使用 localStorage 作为可信来源。
- localStorage 只能用于非关键 UI 偏好，例如展开状态或列宽。
- loading / empty / error / partial data 状态必须显式处理。
- 对任何 `not_comparable`、`inconclusive`、`needs_human_review` 都要有可见状态，而不是空白或隐式失败。

