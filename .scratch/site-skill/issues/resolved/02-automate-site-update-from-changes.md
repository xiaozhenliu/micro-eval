---
id: LOCAL-SITE-SKILL-02
title: 根据源码变更自动驱动站点更新
effort: site-skill
type: task
status: resolved
triage: ready-for-agent
executor: agent
blocked_by: []
created_at: 2026-08-29T16:38+08:00
updated_at: 2026-08-29T16:38+08:00
---

# LOCAL-SITE-SKILL-02 — 根据源码变更自动驱动站点更新

## What to build

把 `micro-eval-site` 从站点规格说明升级为三层可执行工作流：影响分析层读取
git 变更并生成计划；内容更新层由调用 skill 的 agent 根据当前源码与 diff
实际更新中英内容；测试检验层独立核对影响处置清单、实际页面 diff、双语完整性
和专项测试，任何一层不闭合都不能完成。

## Acceptance criteria

- skill 自带无第三方依赖的变更影响分析脚本，默认分析相对 `HEAD` 的工作树，
  并允许指定比较基线或注入路径进行验证。
- 项目级影响映射覆盖 CLI、schema、执行/沙箱、评分、决策/趋势、trace、
  Team Server、Web UI、examples、版本/安装和安全等站点内容域。
- 分析结果包含变更文件、命中规则、候选中英页面、专项验证、未映射行为路径
  与语言镜像缺口，并支持人读和 JSON 输出。
- strict 模式对未映射行为路径、失效候选页面或语言镜像缺口 fail closed。
- skill 明确要求 agent 执行页面修改或逐条说明无文档影响，不能只输出分析报告。
- 独立 verify 流程要求每条影响规则都有 updated 或 no-doc-impact 处置；updated
  页面必须出现在实际 diff 中并满足双语成对，no-doc-impact 必须带理由。
- verify 流程自动运行 VitePress production build、`git diff --check` 和影响域映射的
  源码测试；计划过期、测试失败或处置不完整时返回非零。
- 实现后补充行为测试，并通过 skill 校验、脚本测试、真实工作树分析、站点构建、
  public projection 与 work governance 校验。

## Completion evidence

- 三层工作流：`.agents/skills/micro-eval-site/SKILL.md`。
- 自动化入口：`.agents/skills/micro-eval-site/scripts/site_update.py`。
- 影响映射：`.agents/skills/micro-eval-site/references/site-impact-map.toml`。
- 行为测试：`.agents/skills/micro-eval-site/tests/test_site_update.py`。
- Development log：`docs/dev/log/2026-08-29-1638-dev-log-automated-site-update-skill.md`。
- 验证：skill 行为测试 10 项、CLI contract 28 项、UI contract 115 项、
  VitePress production build、真实 git `plan → verify`、skill 结构校验、
  public projection、work governance 与 diff checks 均通过。
