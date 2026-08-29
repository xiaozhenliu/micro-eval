---
id: LOCAL-MONID-01
title: 安装项目级免费搜索 skill
effort: monid
type: task
status: resolved
triage: ready-for-agent
executor: agent
blocked_by: []
created_at: 2026-08-29T16:45+08:00
updated_at: 2026-08-29T17:00+08:00
---

# LOCAL-MONID-01 — 安装项目级免费搜索 skill

## What to build

把 Monid 的远程 skill 和 CLI 设置为项目内可共享、公开发布时排除的搜索能力。
免费搜索必须优先使用 Monid 当前标记为免费的 TinyFish search/fetch 端点；不得把
其他按调用或按结果计费的端点误称为免费，也不得在未向用户说明价格时自动消费余额。

## Acceptance criteria

- 保存并启用项目级 `monid` skill，让读取 `.agents/skills` 的 agent 可直接发现。
- 为需要 `.claude/skills` 或 `.codex/skills` 的客户端提供同一 canonical skill 的入口，
  不复制出会漂移的多份正文。
- 安装与远程 skill 版本匹配的 Monid CLI，并完成无需 API key 的基础 setup。
- 补充项目层免费搜索约束，默认发现并检查 `tinyfish/search` 或 `tinyfish/fetch`，
  只有价格明确为零时才可作为“免费搜索”执行。
- 验证 skill 格式、CLI 版本、免费端点发现以及 public projection 私有分类。

## Completion evidence

- Canonical skill：`.agents/skills/monid/SKILL.md`。
- Codex 展示元数据：`.agents/skills/monid/agents/openai.yaml`。
- 共享入口：`.claude/skills/monid` 与 `.codex/skills/monid` 均指向 canonical skill。
- Live 验证：`tinyfish/search` 与 `tinyfish/fetch` 均为 verified、healthy、
  `$0/call`；两次 search smoke 均为 HTTP 200、reported cost `$0`、billed units 0。
- 格式验证：OpenAI `quick_validate.py` 与 Agent Skills `agentskills validate` 通过。
- 私有边界：public projection plan 将 `.agents/**`、`.claude/**`、`.codex/**`
  分类为 private，未出现 unknown path。
- Development log：`docs/dev/log/2026-08-29-1700-dev-log-monid-free-search-skill.md`。
