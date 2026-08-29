---
title: LOCAL-SITE-SKILL — Project site skill workstream map
doc_type: reference
status: active
created_at: 2026-08-29T18:09+08:00
updated_at: 2026-08-29T18:09+08:00
owner: micro-eval maintainers
source_of_truth: true
tags:
  - work-record
  - workstream-map
related:
  - docs/agents/issue-tracker.md
---

# LOCAL-SITE-SKILL — Project site skill workstream map

## Scope

Creation and maintenance of the project-local `micro-eval-site` skill,
including its routing description, shared installation paths, UI metadata,
and repository-specific site synchronization workflow.

## Boundaries

Ordinary bilingual site content changes belong to the product workstream that
caused them. General skill infrastructure, release publication, and unrelated
frontend work do not belong here.

## Decisions-so-far

- `LOCAL-SITE-SKILL-01` — [创建项目站点更新 skill](issues/resolved/01-create-project-site-skill.md)
- `LOCAL-SITE-SKILL-02` — [自动化站点影响分析与更新](issues/resolved/02-automate-site-update-from-changes.md)
- `LOCAL-SITE-SKILL-03` — [补全站点 skill 的 UI 元数据](issues/resolved/03-complete-skill-ui-metadata.md)
