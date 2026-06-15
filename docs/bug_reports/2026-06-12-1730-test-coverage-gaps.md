---
title: 测试覆盖缺口清单（Phase 1 / Phase 2 复盘）
doc_type: analysis
status: resolved
created_at: 2026-06-12T17:30+08:00
updated_at: 2026-06-12T17:30+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - review
  - test-coverage
  - security
related:
  - docs/superpowers/plans/2026-06-12-phase2-implementation-plan.md
  - docs/superpowers/specs/2026-06-02-test-architecture.md
  - docs/engineering/security-development-guidelines.md
---

# 测试覆盖缺口清单（Phase 1 / Phase 2 复盘）

> **修复状态（2026-06-12）**：三处缺口已补齐，新增 17 个测试（109 passed）。
> 覆盖率达标：langfuse_provider 80%、validator 94%、run_store 96%，总覆盖 73% → 77%。
> 新增文件：`tests/unit/test_langfuse_provider.py`、`tests/unit/test_validator.py`、
> `tests/unit/test_run_store_boundaries.py`。

## 1. 背景

Phase 2 收口后用 `pytest --cov` 复盘（92 tests，总覆盖 73%），确认三处需要补
契约/验收测试的缺口。CLI 层的 0% 是统计假象（e2e 走 subprocess 不计入），
不在补测范围；执行层错误分支（adapter/workspace 79%）风险低，亦不补。

## 2. 缺口 1：`trace/langfuse_provider.py` 覆盖率 0%（优先级最高）

P2-b 验收标准明确要求的两条没有对应测试：

- 假凭证/不可达 host 时降级为 process provider，run 正常完成；
- `LANGFUSE_SECRET_KEY` 值不得出现在任何持久化产物中。

`from_env()` 的三个分支（无凭证、SDK 缺失、实例化异常）与 `collect()` 的
cost ladder 标注（`langfuse_cost` / `langfuse_tokens` / `unavailable`）、
summary redaction、external_url 拼接均未被触达。这是安全验收项，
不是普通覆盖率问题。

**补测**：`tests/unit/test_langfuse_provider.py`，用 fake client 注入，
覆盖降级三分支 + cost ladder 三档 + summary 脱敏 + TraceRef 序列化不含 secret。

## 3. 缺口 2：`evaluation/validator.py` 覆盖率 52%

deterministic validation 是评分权威路径（P5；judge 不得覆盖其失败结论），
但以下分支无测试：

- `exit_code` expectation（85-87 行）；
- `file_exists` expectation，**含 path-escape 防护**（96 行的
  `_is_relative_to` 检查）；
- `command` expectation 全路径（112-138 行）：成功/失败、**cwd 逃逸 cell
  目录的拒绝**（117-118 行）、超时、command not found、输出 redaction、
  env 白名单；
- `stderr` stream 选择（107 行）；
- unsupported expectation type 兜底（100 行）。

其中两处 path-escape 检查属于 security-guidelines 的 workspace 边界要求，
应有契约测试钉住。

**补测**：`tests/unit/test_validator.py`，每个分支至少一例，
path-escape 与 redaction 必须显式断言。

## 4. 缺口 3：`store/run_store.py` 覆盖率 72%

未覆盖部分恰好是兼容性与边界承诺：

- `run_dir()` 的 output_dir 逃逸 project root 时抛 `RunStoreError`
  （33-34 行，workspace 边界）；
- `list_runs()` 的 legacy 扁平 JSON fallback 与坏文件容错（151-170 行）
  ——这是 Phase 2「旧 run 可读」验收承诺的一部分；
- `latest_run_id()`（174-186 行）。

**补测**：在 `tests/unit/test_decision_store.py` 或新文件中补
escape-raises、legacy fallback、latest_run_id 三类用例。

## 5. 验收标准

- `uv run pytest -q` 全绿；
- `langfuse_provider.py` 覆盖率 ≥ 80%，`validator.py` ≥ 90%，
  `run_store.py` ≥ 85%；
- 新增测试不引入网络依赖（Langfuse 用 fake client，不 import 真 SDK）。
