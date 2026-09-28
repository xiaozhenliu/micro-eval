---
title: "micro-eval Frontend Guidelines"
language: en
authoritative: true
date: 2026-06-02
updated_at: 2026-09-27T16:00+08:00
status: draft
type: engineering-guidelines
tags:
  - engineering
  - frontend
  - nextjs
  - micro-eval
---

# micro-eval Frontend Guidelines

Scope: `ui/`.

## Stack

- Next.js 16.
- React 19.
- TypeScript strict mode.
- Zod v4.
- Tailwind CSS v4.

## Data Access

- The UI never trusts filesystem JSON directly.
- All run / cell / artifact / evaluation data passes a zod parse.
- API routes / server components read project data through a unified data access layer.
- The project root is injected from configuration or environment variables; it is never hardcoded inside components.
- Components consume typed data only and never touch raw filesystem paths, except the artifact viewer.

## Component Boundaries

Components are organized around product objects:

- RunList
- MatrixHeatmap
- CellDetail
- TraceViewer
- ComparisonTable
- ConfigEditor
- CostPanel
- AnnotationPanel
- DecisionSummary
- CaveatBanner
- WorkspaceCard (Team Server, v0.4)
- QueueDashboard (Team Server, v0.4)
- QueueJobCard (Team Server, v0.4)
- RunEnqueueButton (Team Server, v0.4)
- TemplateCard (Team Server, v0.4)
- MemberBadge (Team Server, v0.4)

Components must not recompute business conclusions. Conclusions come from Decision data. Components only render, filter, sort, drill down, and take human input.

## UI State

- Human evaluation must persist to backend data files; localStorage is never a trusted source.
- localStorage may only hold non-critical UI preferences such as expansion state or column widths.
- Loading / empty / error / partial-data states must be handled explicitly.
- Every `not_comparable`, `inconclusive`, or `needs_human_review` gets a visible state, never a blank or silent failure.
