---
id: LOCAL-WORK-GOVERNANCE-04
title: 把 ticket 模板从 AGENTS.md 移到独立文档
effort: work-governance
type: governance
status: resolved
triage: ready-for-agent
executor: agent
blocked_by: []
created_at: 2026-08-29T17:06+08:00
updated_at: 2026-08-29T17:10+08:00
tags:
  - governance
  - ticket
related:
  - docs/agents/issue-tracker.md
  - docs/agents/ticket-template.md
---

# LOCAL-WORK-GOVERNANCE-04 — 把 ticket 模板从 AGENTS.md 移到独立文档

## What to build

`AGENTS.md` 是每个 session 常驻上下文的仓库级 guardrail，只应承载严格要求和
引用，不应内联 ticket front matter 模板与字段枚举。把可照抄的细节移入一个
独立的、极小的模板文档，`AGENTS.md` 只保留强制性要求并指向它。

同时消除枚举重复：模板用一组真实可用的默认值（`type: task` /
`status: ready` / `triage: ready-for-agent` / `executor: agent`），而不是把
`triage-labels.md` 的取值表复制一份，避免出现第三处需要同步的词表。

## Acceptance criteria

- 新增 `docs/agents/ticket-template.md`：只含可照抄的 front matter 骨架、
  最易写错的几条约束、body 章节清单，以及指向权威文档的一行引用。
- 模板不复制 `triage-labels.md` 的取值表；非默认取值由 `triage-labels.md`
  提供。
- `AGENTS.md` 移除内联 YAML 骨架，改为严格要求 + 对模板与契约文档的引用。
- `.codex/skills/micro-eval-release/assets/templates/agents-publish-template.md`
  与 `AGENTS.md` 保持逐字一致。
- `docs/agents/issue-tracker.md` 在契约中指向该模板，说明模板是写作入口、
  契约文档是权威来源。
- 校验只在提交前跑一次：`scripts/check-work-governance.py` 与
  `tests/integration/test_release_to_main.py` 通过。

## Completion evidence

- 模板：`docs/agents/ticket-template.md`（可照抄骨架 + 易错点 + resolve 前动作）。
- `AGENTS.md` 与
  `.codex/skills/micro-eval-release/assets/templates/agents-publish-template.md`
  移除内联 YAML，改为两条强制要求 + 引用；两者逐字一致。
- `docs/agents/issue-tracker.md` 声明自身是契约、模板是写作入口，并加入 related。
- 无枚举重复：模板只给默认值，非默认取值指向 `docs/agents/triage-labels.md`。
- 验证（提交前一次性执行）：`uv run python scripts/check-work-governance.py`、
  `uv run pytest tests/integration/test_release_to_main.py`、`git diff --check`。
