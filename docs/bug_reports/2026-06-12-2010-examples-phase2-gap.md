---
title: Examples 未跟进 Phase 2 能力
doc_type: analysis
status: resolved
created_at: 2026-06-12T20:10+08:00
updated_at: 2026-06-12T20:10+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - review
  - examples
  - onboarding
  - phase2
related:
  - examples/README.md
  - examples/agent-codefix-showdown/README.md
  - docs/dev/log/2026-06-12-1935-dev-log-v0-2-1-test-architecture-gaps.md
---

# Examples 未跟进 Phase 2 能力

> **修复状态（2026-06-12）**：按方案完成。实测 mock run 的 decision.json 中
> `pass_at_k: {1: 1.0, 2: 1.0, 3: 1.0}`、无 low_sample caveat、3 条 process
> TraceRef；两份 yaml `micro-eval validate` 通过；pytest 122 passed。

## 问题

v0.2.x 交付了 Phase 2 全部能力，但 `examples/` 只被动获得了 schema 兼容
（`evaluation:` 块含 `denominator_policy`），没有展示任何 Phase 2 能力。
示例是 10 分钟上手路径的载体（BRD 成功标准），与产品当前能力脱节会直接
影响新用户对产品价值的感知。

具体缺口：

1. **repetitions 全为 1** —— pass@k/pass^k 聚合（Phase 2 头牌能力）在
   示例中不可见，且 `low_sample` caveat 常驻，给用户错误信号；
2. **无 `trace:` 块** —— 根目录 `eval.yaml.example` 已有示例，examples
   两个 yaml 均没有；
3. **无 `judge:` 块** —— 同上，LLM judge 路径不可见；
4. **两个 README 停留在 MVP 表述** —— 未提复盘页 `/run/[id]/review`、
   pass@k、cost source、decision.json。

## 修复方案

成本约束：不给真实 agent 矩阵加 repetitions（4 agents × 3 reps 的真实
LLM 成本不可接受）；Phase 2 展示集中在零成本的 deterministic mock 路径。

1. `eval.mock.yaml`：`repetitions: 1 → 3`（mock 确定性、零成本），新增
   `trace:`（enabled: true, provider: process）与 `judge:`（disabled，
   注释说明如何启用）块；
2. `eval.yaml`（真实 agent 路径）：仅追加注释掉的/disabled 的 `trace:`
   与 `judge:` 示例块，不改 repetitions；
3. 两个 README：新增「Phase 2 能力怎么看」小节（report 的 pass@k、
   `decision.json`、复盘页路径、cost source 含义），刷新 frontmatter
   updated_at 与能力描述。

## 验收标准

- `python examples/run-example.py` 正常退出；
- mock run 产物 `decision.json` 中 mock-local 的 `pass_at_k` 非空、
  caveats 不含 low_sample（3 次成功重复）；
- `uv run micro-eval validate`（示例目录）对两份 yaml 均通过；
- `uv run pytest -q` 全绿（examples 冒烟在交付门槛内）。
