---
title: Dev 分支审查发现的问题清单
doc_type: analysis
status: resolved
created_at: 2026-06-12T15:21+08:00
updated_at: 2026-06-12T17:10+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - review
  - bug-report
  - dev
  - security
  - evaluation
related:
  - docs/engineering/security-development-guidelines.md
  - docs/engineering/security-service-guidelines.md
  - docs/engineering/implementation-principles.md
  - docs/superpowers/plans/2026-06-12-phase2-implementation-plan.md
---

# Dev 分支审查发现的问题清单

> **修复状态（2026-06-12）**：两项缺陷均已修复并通过验收（pytest 92 passed、vitest 全绿）。
> 问题 1 采用方案 1：denominator_policy 经 RunPlan/RunRecord 端到端贯通，UI 重算同步。
> 问题 2：judge prompt 所有外部来源字段先脱敏再截断，redactor 为必填参数。
> 详见 `docs/dev/log/2026-06-12-1640-dev-log-blocker-fixes-denominator-judge-redaction.md`。

## 1. 范围与验证

本文件记录一次对当前 `dev` 分支未提交改动的审查结果。审查重点放在：

- 决策聚合是否真的消费了新配置；
- LLM judge 路径是否满足安全规范中的 redaction 要求；
- UI / Python 双端是否保持一致。

已执行的验收测试：

```bash
uv run pytest tests/unit/test_aggregation.py tests/unit/test_trace_provider.py tests/unit/test_llm_judge.py tests/unit/test_decision_store.py tests/unit/test_config_loader.py tests/e2e/test_p0b_reproducibility_flow.py -q
```

结果：`44 passed`

测试通过并不代表问题不存在；下面两项是通过源码审查确认的真实缺陷。

## 2. 问题 1：`denominator_policy` 已解析但未真正生效

**严重度：阻断**

### 现象

`eval.yaml` 里已经可以配置 `evaluation.denominator_policy`，`ProjectConfigV2` 也会把它纳入 `config_hash`，但当前执行和决策路径没有把这个值真正用进去。结果是：

- Python 侧 `build_decision()` 始终走默认聚合行为；
- UI 侧的重算逻辑也硬编码为 `include_failed`；
- 用户在配置中切换到 `exclude_failed` 时，实际 pass rate / pass@k 不会按预期变化。

### 关键证据

- `src/micro_eval/config/loader.py`
  - 已把 `evaluation` 解析进配置对象。
- `src/micro_eval/decision/summary.py:11-58`
  - `build_decision(record)` 调用 `build_aggregation(record.results, traces=record.traces)`，没有传入任何 denominator policy。
- `src/micro_eval/decision/aggregation.py:16-74`
  - `build_aggregation()` 和 `aggregate_configuration()` 虽然支持 `denominator_policy` 参数，但上游没有喂值。
- `ui/src/lib/evaluation.ts:95-158`
  - `recomputeDecision()` 直接把 `denominator_policy` 写死为 `"include_failed"`。

### 影响

这是一个“配置存在但行为不变”的功能缺陷，会让评测结果和用户配置不一致，也会误导后续的比较分析。

### 建议修复

二选一：

1. 端到端贯通 `denominator_policy`，让配置真正参与聚合与 UI 重算；或
2. 在能力未完成前移除/冻结这个配置入口，避免误导用户。

## 3. 问题 2：LLM judge prompt 未先脱敏就发送给外部模型

**严重度：阻断**

### 现象

当前 LLM judge 路径会把以下内容原样拼进 prompt 并发送给 judge provider：

- `cell.task.input_payload`
- `cell.task.expected_output`
- `adapter_result.output` / `adapter_result.stdout`
- `adapter_result.stderr`
- validation evidence 摘要

虽然返回后的 `rationale` 会经过 `redactor.redact()`，但**发送出去的 prompt 本身没有脱敏**。如果 agent 输出、stderr 或 task 输入里含有 `MICRO_EVAL_SECRET_*` 相关内容，这些内容会被外发到 judge 服务。

### 关键证据

- `src/micro_eval/evaluation/llm_judge.py:110-173`
  - `build_judge_prompt()` 直接拼接原始文本；
  - `evaluate_cell_with_judge()` 只对 `outcome.rationale` 做 redaction。
- `docs/engineering/security-development-guidelines.md`
  - 明确要求：任何会持久化或返回给 UI/API 的文本证据都必须先 redaction；新增输出路径要重新检查 secret 泄漏风险。

### 影响

这是一个真实的 secret 泄漏面。即使 judge 是可选能力，只要配置启用，就可能把敏感内容发送到外部模型或第三方服务。

### 建议修复

在构造 prompt 之前先对所有可泄漏字段做 redaction，至少覆盖：

- stdout / output / stderr
- task input / expected output
- validation evidence

如果需要保留原文用于本地审计，应只保留在本地受控存储中，不要进入外部 judge 请求体。

## 4. 当前结论

这两项都不是测试风格问题，而是实质性缺陷：

1. 一个是“配置无效”的功能正确性问题；
2. 一个是“外发前未脱敏”的安全问题。

建议先修这两项，再继续扩展 Phase 2 的审查范围。
