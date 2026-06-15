---
title: "micro-eval 测试架构设计"
date: 2026-06-02
updated: 2026-06-12
status: active
type: design
tags:
  - testing
  - test-architecture
  - micro-eval
---

# micro-eval 测试架构设计

> 本文档定义 micro-eval **自身代码**的测试策略。它是 [[2026-06-02-unicorn-design]] Part I §5 模块契约的**投影**：
> 每个模块的 Validation checklist / Failure modes / Must not bypass 在这里落成具体测试规格。
> 它引用 Unicorn，不重定义 Unicorn。冲突时以 Unicorn Part I 为准。
>
> **范围边界**：本文档讲"如何测试 micro-eval 的 Python/TS 代码"，**不**讲"micro-eval 如何给 agent 打分"
> （后者是产品功能，见 Unicorn §4–§5）。两者极易概念串台——本文档严格只谈前者，dogfooding 单列 §8。

## 1. 测试不变量（长期稳定）

以下约束不随框架选型或实现阶段改变：

1. **契约即测试来源** — 测试不是自由发挥；Unicorn §5 每个模块的 Validation checklist / Failure modes 必须有对应测试（对齐 Unicorn §2 不变量 #12）。
2. **确定性优先，零容忍 flaky** — 测试本身必须确定性。禁止依赖 wall-clock、`Math.random()`、网络、真实 LLM 调用、未固定的 subprocess 时序。flaky 测试视为 bug，立即 quarantine 或修复。
3. **跨语言契约对等** — 同一份 schema 的 Pydantic（Python）与 zod（TS）表示必须经测试验证字段、可空性、enum 对等（直接回应 Unicorn §10 记录的"两端不对齐"债）。
4. **测真实行为，不测实现细节** — 优先测模块的 Inputs→Outputs 契约，而非内部私有方法；重构不应连带改大量测试。
5. **不变量必须有否定测试** — "Must not bypass"类约束（如 deterministic 失败不可被 LLM 翻转、secrets 永不进 evidence）必须有断言其**被拒绝**的测试，而非只测正路径。
6. **测试随迁移分期演进，但不变量不变** — 框架、覆盖率目标、有哪些测试随 M0–M4 变化；§1 这几条不变。

## 2. 测试金字塔与分层

```text
        ╱╲        E2E（少）       micro-eval run → JSON → report，全链路
       ╱  ╲       Integration     多模块协作：Kernel+Adapter+Workspace
      ╱────╲      Contract        Pydantic↔zod parity；模块 I/O schema
     ╱      ╲     Unit（多）       单模块纯函数：scorer、loader、aggregator
    ╱────────╲
```

| 层 | 测什么 | 工具 | 当前状态（2026-06-12，v0.2.1） |
|---|---|---|---|
| Unit | 单模块逻辑、纯函数、边界 | pytest（Py）/ vitest（TS） | Py 89 个；TS 3 个（evaluation 纯函数） |
| Contract | 跨模块对象 schema、跨语言 parity | pytest + 生成/校验 | 已落地：canonical（P0 + Phase 2）与 legacy fixture 双端校验 |
| UI Route Contract | API route 消费 Python 产物、zod 严格解析 | vitest + 共享 fixture | 已落地（§4.1，10 用例） |
| Integration | 多模块协作、Provider 解析 | pytest + 受控 subprocess | 部分（runner、kernel、store） |
| E2E | CLI 全流程、产物结构 | pytest + tmp project | 33 个：Phase 1 链路 + Phase 2 黄金路径 + legacy 兼容 + CLI 失败路径 |
| UI | 组件渲染、run viewer | vitest + Testing Library | 关键断言已落地（Decision Surface 诚实性 2 用例），不做系统性组件测试 |

## 3. 按模块的测试规格（投影自 Unicorn Part I §5）

每个模块的测试来源是 Unicorn §5 中对应的 **Must not bypass** 与 **Failure modes**。

### 3.1 Asset Layer

| 测试类型 | 验证什么 | 层级 |
|---|---|---|
| `task_id` / `task_revision_id` 稳定性 | 同一 YAML 内容 → 相同 revision hash；改一行 → 不同 hash | Unit |
| legacy `input_payload` → `prompt` 投影 | 旧格式 task 能被加载、新字段存在 | Unit |
| 坏 task 检测 | 缺 workspace / 缺 expectations / scope 过大 → 明确警告（不 silent pass） | Unit |
| rubric_ref 稳定性 | inline rubric 改动 → rubric hash 变化 | Unit |
| schema 校验 | 不合法 YAML → ConfigError + 人类可读 message | Unit |

**否定测试**：空 task_id → 拒绝；expected_output 不能绕过 expectations 约束。

### 3.2 Configuration Layer

| 测试类型 | 验证什么 | 层级 |
|---|---|---|
| `configuration_id` 生成确定性 | 同一 agent+skill+env+params → 同一 digest | Unit |
| baseline/candidate 是 2-column matrix | legacy 格式产出的 RunPlan 有 2 个 Configuration | Unit |
| repetition identity 保留 | repetitions=3 → RunPlan 有 3×N cells | Unit |
| guardrails 验证 | timeout / max_concurrent / budget 缺失时有 defaults；budget=0 → 拒绝 | Unit |
| EvaluationContract 最小字段 | 缺 comparison_subject → 拒绝 | Unit |

**否定测试**：configuration_id 不能只靠 agent display name。

### 3.3 Execution Kernel

| 测试类型 | 验证什么 | 层级 |
|---|---|---|
| 超时中断 | agent 超时 → status=timeout + latency 记录 | Integration |
| 并发上限 | max_concurrent=2 + 5 cells → 最多 2 个同时执行 | Integration |
| 失败不影响其他 cell | 一个 cell error → 其他 cell 仍完成 | Integration |
| ExecutionResult 形状不含结论 | 结果只有 exit/latency/output_refs，无 score/verdict | Unit |
| retry 行为 | retry=1 + 第一次失败 → 第二次尝试 | Integration |

**否定测试**：Kernel 不能硬编码 CommandAdapter 命令细节（接口隔离）。

### 3.4 Agent Adapter Layer

| 测试类型 | 验证什么 | 层级 |
|---|---|---|
| stdin 模式 | input 从 stdin 传入 → agent 收到 | Integration |
| file 模式 | input 写文件 + path 传入 → agent 收到 | Integration |
| output=directory | agent 写入 output_dir → artifacts 被收集 | Integration |
| exit code 语义 | exit 0=pass, 非零=error + failure_mode 记录 | Integration |
| argv 安全（无 shell 注入） | task payload 含 `; rm -rf /` → 不被 shell 展开 | Unit |
| env allowlist | 只注入声明的 env vars | Unit |
| SkillInjection decorator | 装饰后 workspace 内有 skill 文件 + invocation 不变 | Unit |

**否定测试**：shell 字符串插值 → 被拒绝或标记为 legacy risk（当前仍存在，测试标记为 xfail / migration）。

### 3.5 Environment / Reproducibility Layer

| 测试类型 | 验证什么 | 层级 |
|---|---|---|
| git worktree 创建 / 清理 | create → 独立目录 + 正确 commit；cleanup → 无残留 | Integration |
| SameStartSnapshot 完整性 | snapshot 包含 git_commit / config_hash / python_version / timestamp | Unit |
| 非 git 目录 fallback | 不在 repo 时 → temp dir + snapshot 标记不完整 | Unit |
| diff 收集 | agent 改文件 → collect_diff 返回 patch | Integration |

**否定测试**：snapshot 缺关键字段时 → Decision 不能给 strong verdict（跨模块 contract 测试）。

### 3.6 Artifact / Trace Layer

| 测试类型 | 验证什么 | 层级 |
|---|---|---|
| ArtifactRef 稳定 ID | 同内容 → 同 artifact_id | Unit |
| stdout/stderr 存储 | 执行后 artifact 可按 run_cell_id 取回 | Integration |
| output_summary 是 excerpt | 超长输出截断到 500 字符 | Unit |
| EvidenceItem 结构 | 类型 + source + summary + artifact_ref 齐全 | Unit |
| secret redaction | env 里有 API key → artifact 中不出现值 | Unit |

**否定测试**：raw stdout 不能直接成为 EvidenceItem（必须经结构化）。

### 3.7 Evaluation Layer

| 测试类型 | 验证什么 | 层级 |
|---|---|---|
| exact match scorer | 完全匹配=1.0, 部分匹配=0.8, 不匹配=0.0 | Unit |
| pass/fail threshold | score < threshold → failed | Unit |
| EvaluationResult 引用 evidence | 评分结果必须有 evidence_refs | Unit |
| ScoreStage pipeline | stages 按顺序执行；should_run=False → 跳过 | Unit |
| Aggregator 不翻转 deterministic 失败 | validation critical failure + LLM 高分 → 结果仍 failed | Unit |

**否定测试（关键）**：LLM judge 不能覆盖 deterministic 关键失败——即使 judge 给满分。

### 3.8 Decision Layer

| 测试类型 | 验证什么 | 层级 |
|---|---|---|
| verdict taxonomy | 结果只能是 improved/regressed/mixed/inconclusive/not_comparable | Unit |
| snapshot gate 失败 → 结论受限 | gate=fail → verdict=not_comparable | Unit |
| evidence citation | report 中每个 claim 有 evidence_id 引用 | Unit |
| Basic Honest Stats | pass rate / mean latency / cost / 低样本警告正确计算 | Unit |
| inconclusive 是合法结果 | n=1 且结果摇摆 → 不强行给 winner | Unit |

**否定测试**：snapshot mismatch 时不允许 verdict=improved/regressed。

## 4. 跨语言契约测试（Pydantic ↔ zod）

**问题**：当前 Pydantic schema（Python）与 zod schema（TS UI）不完全对齐（如 `git_commit` 可空性不一致）。

**策略**：

```text
Pydantic model ──► 生成 JSON 样本 ──► zod.parse(样本) 必须成功
                     │
                     └── 包含 edge cases：null fields, enums, empty arrays
```

具体做法（**已实施，v0.2.2**）：
1. `scripts/generate-golden.py` 用 Pydantic 确定性生成
   `tests/contract/golden/*.json`（典型 + 边界变体 + legacy v0.1.x）。
2. `tests/contract/test_golden.py` 做 round-trip、幂等与 no-secrets 断言。
3. `ui/src/lib/__tests__/golden-contract.test.ts` 用 zod 消费同一批文件，
   并做 stripped-field 检查（zod 默认忽略未知字段，必须显式比对字段集合
   才能抓到「Python 多出字段」方向的漂移）。
4. CI `golden-sync` job：重新生成后 `git add -A` + `git diff --cached
   --exit-code`——任一端改 schema 不同步即红（双向漂移均已注入实验验证）。

需要覆盖的关键 schema：
- `Run` / `RunResult` / `EnvironmentSnapshot`（当前 legacy）
- Phase 2 已落地、需纳入 parity 的：`RunPlan` / `EvaluationResult` /
  `DecisionReport`（含 `AggregationResult` / `denominator_policy`）/ `TraceRef`

### 4.1 UI API route 契约集成测试（Phase 2 后新增层级）

> 登记自 `docs/bug_reports/2026-06-12-1810-e2e-integration-test-gaps.md` ISSUE-1（P0）。

`/api/runs/[id]` 与 `/api/runs/[id]/cells/[cellId]/trace` 是 Python 写端
（Pydantic → `.micro-eval/` JSON）与 TS 读端（route handler → zod）之间的
跨语言契约边界，必须有独立测试层：

1. 共享 fixture 由 Python 侧真实产出（扩展 `canonical-run-p0.json` 机制至
   Phase 2 字段：decision.json、TraceRef、judge EvaluationResult）；
2. vitest 中 route handler 读取该 fixture，响应必须通过 zod schema 严格解析；
3. 任一端 schema 演进而另一端未同步 → 测试红。

这一层与 §4 的 golden JSON parity 互补：parity 测 schema 形状对等，
本层测 route handler 的真实消费路径（含文件读取、路径解析、错误分支）。

## 5. 当前状态 vs 目标（对齐 Unicorn §10 M0–M4）

| 迁移阶段 | 测试状态 | 目标测试增量 |
|---|---|---|
| **M0 文档对齐**（现在） | ~25 pytest unit + 1 e2e；vitest 未落地 | 补本文档；不改代码 |
| **M1 Schema bridge** | +contract tests | Pydantic↔zod parity tests；configuration_id 生成 |
| **M2 Evidence/Snapshot bridge** | +snapshot gate tests | SameStartSnapshot 完整性；Evidence 结构 |
| **M3 Adapter/Workspace hardening** | +integration | argv 安全；worktree 接入 run flow；secret redaction |
| **M4 Modular expansion** | +ScoreStage pipeline | ScorePipeline 顺序；Aggregator 不翻转；multi-config |

覆盖率目标（渐进）：
- M1 后：Python unit ≥ 60%
- M3 后：Python unit + integration ≥ 75%；UI ≥ 40%
- M4 后：总体 ≥ 80%

当前实际（2026-06-12，v0.2.1）：Python 总覆盖 78%（122 tests）+ vitest 18 tests；
关键模块：aggregation 97%、validator 94%、run_store 96%、langfuse_provider 80%
（剩余为真实 SDK 路径，按 §6 mock 策略有意不测）。

### 5.1 Phase 2 收口后登记的测试缺口（已实施，v0.2.1）

> 登记自 `docs/bug_reports/2026-06-12-1810-e2e-integration-test-gaps.md`（已 resolved）。
> 五项均已于 v0.2.1 交付：Python 122 tests、vitest 18 tests。

| Issue | 层级 | 内容 | 严重度 |
|---|---|---|---|
| ISSUE-1 | UI Route Contract（§4.1） | API route 跨语言契约集成测试 | P0 |
| ISSUE-2 | E2E | Phase 2 全开黄金路径（trace + judge mock + decision.json + report） | P0 |
| ISSUE-3 | E2E + Contract | v0.1.x 旧 run 固化 fixture，report 与 zod 双端可消费 | P1 |
| ISSUE-4 | E2E | CLI 失败路径契约（退出码 + 报错文案，subprocess） | P2 |
| ISSUE-5 | UI | Decision Surface 诚实性断言（不显示 winner、low_sample 可见） | P2 |

两个 P0 已在 Phase 3 执行链路改动（Docker sandbox、复杂 workspace）
动工前完成；Phase 3 改动以 ISSUE-1/2 的测试为主要回归防线。

## 6. 测试数据 / Fixtures / Mock 策略

### Fixtures

```text
tests/
├── fixtures/
│   ├── tasks/              # 标准测试 task YAML（good + bad）
│   ├── configs/            # 标准 eval.yaml（baseline/candidate + matrix）
│   ├── golden/             # Pydantic 生成的 golden JSON（供 contract tests）
│   ├── legacy/             # 旧版本（v0.1.x）run.json 固化样本（兼容性回归，ISSUE-3）
│   └── repos/              # 小 git repo fixtures（用于 workspace tests）
├── unit/
├── contract/
├── integration/
└── e2e/
```

### Mock 策略

| 被 mock 的外部 | Mock 方式 | 原因 |
|---|---|---|
| Agent subprocess | 受控 echo 脚本（exit 0/1/timeout） | 确定性、无真实 LLM 成本 |
| LLM judge（DeepEval/Anthropic） | pytest monkeypatch → 固定 JSON | 不依赖网络和真实模型 |
| Langfuse | fake client 注入（不 import 真 SDK） | 测降级分支、cost ladder、脱敏；真实 SDK 实例化路径有意不测 |
| 文件系统 | tmp_path（pytest 内建） | 隔离、可清理 |
| git | tests/fixtures/repos/ 真实小 repo | worktree tests 需要真实 git |
| wall-clock | `time.monotonic()` monkeypatch 或 freezegun | 确定性 latency 断言 |

### 关于真实 LLM 调用

- 常规 CI：**一律 mock**，0 API 成本。
- 可选 `@pytest.mark.llm_integration` 标记：手动或 nightly 跑，需要真实 API key。
- LLM integration tests 不决定 CI 红绿——只做信号。

## 7. CI 与覆盖率门槛

> **已实施（v0.2.2）**：`.github/workflows/ci.yml` 落地五个 job——
> python-tests（3.11/3.12 矩阵，`--cov-fail-under=75`）、python-quality
> （compileall + shell-injection grep 门禁）、golden-sync（重新生成 golden
> 后 `git add -A` + `git diff --cached --exit-code`）、ui-tests
> （lint + vitest + build）、example-smoke。CI 无 secrets，token 只读。
> 下面的 yaml 保留为最初设计意图。

```yaml
# 目标 CI pipeline（渐进启用）
jobs:
  python-unit:
    run: uv run pytest tests/unit/ --cov=micro_eval --cov-fail-under=60
  python-contract:
    run: uv run pytest tests/contract/
  python-integration:
    run: uv run pytest tests/integration/
  python-e2e:
    run: uv run pytest tests/e2e/
  ui-unit:
    run: cd ui && npm test -- --coverage --coverageThreshold='{"global":{"lines":40}}'
  ui-contract:
    run: cd ui && npm test -- --testPathPattern=contract
```

门槛策略：
- **不允许覆盖率倒退**（CI 对比 main）。
- **新增模块必须附带对应测试**（PR checklist）。
- **flaky 测试 → 即时 quarantine**（不允许 rerun-until-pass）。

## 8. Dogfooding（用 micro-eval 评测自身）

> **范围限定**：这里的 dogfooding 是**验收级**，不替代 §2–§7 的开发测试。目的是验证产品可用性，不是替代 pytest。

用法：
1. 把 micro-eval 的某个 CLI 改动（比如新 scorer）当作被评测的"agent 改动"。
2. 用 micro-eval 自己创建 tasks、configurations、run，得到 Decision Report。
3. 检验 Decision Report 是否真的帮助判断"改动变好还是变差"。

用途：
- 验证决策闭环是否端到端跑通。
- 暴露 Task Authoring、Evidence Chain、Decision Report 的产品问题。
- 积累真实 task templates。

不能替代的东西：
- 单元级回归检测（dogfooding 太重）。
- 确定性 CI 断言（dogfooding 涉及 LLM/成本）。
- 跨语言 contract parity（dogfooding 只走 Python CLI）。

## 9. 旧章节对照（Part II §5/§7 的 test 描述搬迁）

Part II 原 §7.1 文件结构中提到的 `results/`、`artifacts/`、`aggregations/` 目录——它们是**产品产出**，不是测试 fixture。本文档的 `tests/fixtures/` 是 micro-eval 自身开发的测试输入。

Part II 原 §4 评分系统中提到的 validation commands（`npm test`、`cargo test`）——那是 **micro-eval 给被评测 agent 跑的验证**，不是测试 micro-eval 自己的代码。

这个区分很关键：micro-eval 是评测工具；"测评测工具自身"和"评测工具评测 agent"是两件事。本文档只管前者。
