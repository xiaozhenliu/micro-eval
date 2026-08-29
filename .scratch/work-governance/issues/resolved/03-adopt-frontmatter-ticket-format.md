---
id: LOCAL-WORK-GOVERNANCE-03
title: 用 YAML frontmatter 统一本地 ticket 格式
effort: work-governance
type: governance
status: resolved
triage: ready-for-agent
executor: agent
blocked_by: []
created_at: 2026-08-29T16:52+08:00
updated_at: 2026-08-29T16:57+08:00
tags:
  - governance
  - ticket
related:
  - docs/agents/issue-tracker.md
  - docs/agents/triage-labels.md
  - docs/documentation-standard.md
  - docs/dev/log/2026-08-29-1657-dev-log-frontmatter-ticket-format.md
---

# LOCAL-WORK-GOVERNANCE-03 — 用 YAML frontmatter 统一本地 ticket 格式

## What to build

把本地 ticket 的元数据从「正文里位置不固定的裸文本字段行」改为「文件开头的
YAML frontmatter」，与 `docs/documentation-standard.md` 已有的文档元数据风格
一致，并让 `scripts/check-work-governance.py` 以 fail-closed 的方式强制该格式。

现状问题：

- 字段可以出现在正文任意位置（有的在 H1 之后，有的在 `**What to build:**`
  段落之后），阅读时找不到统一的元数据区。
- 解析器扫描全文任意 `Key: value` 行，正文中的普通冒号句子可能被误当作字段。
- 没有创建/更新时间，无法与 `docs/` 的文档元数据规则对齐。
- 已出现未被发现的取值漂移（`Status: in-progress` 而非 `in_progress`）。

## Acceptance criteria

- `docs/agents/issue-tracker.md` 定义 ticket frontmatter 的必填字段、可选字段、
  取值与 body 结构，并成为该格式的唯一权威来源。
- `docs/agents/triage-labels.md` 与 `docs/documentation-standard.md` 使用同一套
  frontmatter 键名，不再描述裸文本字段行。
- effort 级 `map.md` 也使用 frontmatter，不再用裸 `Type:` / `Status:` 行。
- `scripts/check-work-governance.py` 只从 frontmatter 读取字段：缺失 frontmatter、
  未知键、缺必填键、取值非法、时间戳格式错误、`effort` 与目录不符、H1 与
  `id`/`title` 不一致、正文残留 legacy 字段行，都必须报错。
- 校验脚本保持零第三方依赖，可用 `python3` 直接运行。
- `.scratch/` 下全部现存 ticket 与 map 迁移到新格式，且 `in-progress` 之类的
  历史漂移取值被修正。
- `uv run python scripts/check-work-governance.py` 与
  `uv run pytest tests/unit/test_work_governance.py` 通过，且新增覆盖
  frontmatter 缺失、未知键、legacy 字段残留的回归用例。

## Completion evidence

- 格式权威定义：`docs/agents/issue-tracker.md` 的 `Local ticket contract`
  （front matter 字段表、body 结构、effort map 规则）。
- 键名对齐：`docs/agents/triage-labels.md`、`docs/documentation-standard.md`、
  `AGENTS.md`、`TODOS.md` 与
  `.codex/skills/micro-eval-release/assets/templates/agents-publish-template.md`。
- 强制校验：`scripts/check-work-governance.py` 的 `_parse_frontmatter` 与
  `_check_ticket_frontmatter`；归档 ticket 走同一套校验。
- 迁移：`.scratch/` 下 16 个 ticket 与 2 个 effort map 转为 frontmatter，
  `in-progress` 修正为 `in_progress`。
- Development log：`docs/dev/log/2026-08-29-1657-dev-log-frontmatter-ticket-format.md`。
- 验证：`uv run python scripts/check-work-governance.py` 通过；
  `uv run pytest tests/unit/test_work_governance.py` 10 passed（新增 5 项回归）；
  `uv run pytest tests/unit` 542 passed；`site_update.py plan` 无站点影响；
  `git diff --check` 通过。
