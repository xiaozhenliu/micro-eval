---
id: LOCAL-SITE-SKILL-03
title: 补齐站点 skill UI 元数据
effort: site-skill
type: task
status: resolved
triage: ready-for-agent
executor: agent
blocked_by: []
created_at: 2026-08-29T17:08+08:00
updated_at: 2026-08-29T17:10+08:00
---

# LOCAL-SITE-SKILL-03 — 补齐站点 skill UI 元数据

## What to build

为现有 `micro-eval-site` skill 补充 Codex/ChatGPT 使用的
`agents/openai.yaml`，让 skill 选择器显示清晰名称、简短描述和可直接使用的默认
prompt，同时保持现有自动触发、三层更新工作流、canonical 共享路径与私有发布边界。

## Acceptance criteria

- `agents/openai.yaml` 包含与 `SKILL.md` 一致的 `display_name`、25–64 字符的
  `short_description`，以及显式提到 `$micro-eval-site` 的单句 `default_prompt`。
- 保持 `allow_implicit_invocation: true`，让站点或用户文档更新请求仍可自动匹配。
- 不添加缺少真实文件的图标路径、无关品牌字段或不存在的 MCP 依赖。
- canonical `.agents/skills` 文件能通过 OpenAI 与 Agent Skills 格式校验，
  `.claude`、`.codex` 入口仍解析到同一目录。
- 工作治理、diff checks 与 public projection 私有分类验证通过，并留下 dev log。

## Completion evidence

- UI 元数据：`.agents/skills/micro-eval-site/agents/openai.yaml`。
- canonical 与共享入口：`.agents/skills/micro-eval-site`、
  `.claude/skills/micro-eval-site`、`.codex/skills/micro-eval-site`。
- 格式验证：OpenAI `quick_validate.py` 与 Agent Skills
  `agentskills validate` 均通过；独立 YAML contract 检查通过。
- 行为验证：site skill 原有 10 项测试全部通过。
- 私有边界：public projection plan 无 unknown path，`.agents/**`、
  `.claude/**`、`.codex/**` 保持 private。
- Development log：`docs/dev/log/2026-08-29-1710-dev-log-site-skill-ui-metadata.md`。
