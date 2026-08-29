# LOCAL-SITE-SKILL-01 — 创建项目站点更新 skill

ID: LOCAL-SITE-SKILL-01
Type: task
Status: in_progress
Triage: ready-for-agent
Executor: agent
Blocked by: None

## What to build

创建一个项目级 `micro-eval-site` skill，让项目内支持 Agent Skills 的 agent
能够按同一套项目约束更新 `site/` VitePress 站点。skill 必须以单一内容源共享，
并保持在公开发布投影之外。

## Acceptance criteria

- skill 的权威副本位于 `.agents/skills/micro-eval-site/`，描述能够自动命中站点更新任务。
- skill 记录站点的信息架构、权威内容来源、中英同步、导航与静态资源更新边界。
- skill 要求按变更范围运行可观察的验证，至少包含 VitePress production build。
- Claude Code 与 Codex 的项目级发现路径引用同一份 skill，不复制内容。
- release projection 能把 skill 及其兼容入口分类为 private，公开候选树不包含它们。
- skill 通过 `skill-creator` 的 `quick_validate.py` 校验，并留下 development log 证据。

## Completion evidence

待完成。
