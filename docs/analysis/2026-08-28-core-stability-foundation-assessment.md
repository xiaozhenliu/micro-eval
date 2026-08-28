---
title: micro-eval 核心稳定性与基座就绪度评估
doc_type: analysis
status: active
created_at: 2026-08-28T10:40+08:00
updated_at: 2026-08-28T10:40+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - core-stability
  - foundation-readiness
  - local-core
  - product-readiness
related:
  - docs/engineering/architecture-guardrails.md
  - docs/analysis/2026-08-26-benchmark-compatibility-evaluation.md
  - docs/releases/2026-08-08-v0.4.5-release-evidence.md
---

# micro-eval 核心稳定性与基座就绪度评估

结论很明确：

**现阶段 micro-eval 还不能称为稳定的终端用户产品，但已经拥有值得保留的稳定核心。它可以作为友好入口的基座，不过应先完成一次收敛的“Core Stabilization”，不需要重写。**

我会把当前状态定为：**工程基础扎实，核心执行链仍有 P0 正确性缺口，产品分发尚未闭环。**

| 范围 | 当前判断 |
|---|---|
| canonical 数据模型、RunPlan、Evidence、Decision | 稳定，可作为基座 |
| 本地 subprocess、stdout/exit code/contains 评测 | 基本稳定 |
| workspace/code-change 终态评测 | 不稳定，存在已复现的错误 |
| 静态 HTML 报告 | 可用 |
| 源码 checkout 下的 UI | 构建和测试稳定 |
| wheel 安装后的 UI/Team Server | 不可用 |
| Remote Provider、Conversational Eval | 实验性，不应作为当前基座 |

## 稳定的部分

我实际验证了当前 `dev`：

- Python：617 个测试全部通过。
- UI：115 个测试全部通过。
- Python compile、UI lint、Next.js production build 均通过。
- wheel 和 sdist 构建成功。
- 在干净 Python 3.13 虚拟环境安装 wheel 后，`init → validate → run → report.html` 全部成功。
- cell isolation、timeout、secret redaction、snapshot、schema golden fixture、decision caveat 等都有较完整测试。

因此 [RunPlan/Execution/Evidence/Decision 的领域模型](../engineering/architecture-guardrails.md#决策闭环)不用推倒。它正是未来入口应该复用的基座。

## 当前真正的阻断项

### 1. workspace 在验证前被删除

普通执行路径目前是：

```text
Agent 执行
→ cleanup workspace
→ file_exists / command validator
```

[`kernel.py`](../../src/micro_eval/engine/kernel.py) 在 `finally` 中先 cleanup，之后才调用 validator。

我做了真实最小复现：

- Agent 成功创建 `result.txt`
- stdout 为 `done`
- Agent exit code 为 0
- snapshot 显示 workspace 已成功清理
- `file_exists: result.txt` 却被判定为 `missing`

也就是说，当前最核心的 coding-agent 场景可能产生假失败。617 个测试全部通过，是因为 validator 测试和 workspace cleanup 测试彼此独立，缺少贯穿真实 Kernel 生命周期的验收测试。

### 2. Agent 的代码修改没有形成稳定产物

Workspace Provider 已经定义了 `collect_diff()`，但 Execution Kernel 没有调用它。普通 coding Agent 在 worktree 中修改完代码后：

- workspace 被删除；
- diff 没有进入 Artifact/Evidence；
- validator 又无法在 cleanup 后检查终态。

目前示例主要通过 wrapper 在 workspace 内先运行测试，再把结果写到 `MICRO_EVAL_OUTPUT_DIR`，因此绕开了问题。但这不是通用 CLI Agent 应有的默认行为。

### 3. 安装包与产品能力不一致

干净 wheel 的 CLI 核心可以运行，但：

```bash
micro-eval ui
```

直接返回：

```text
Error: ui/ directory not found.
```

因为 [`main.py`](../../src/micro_eval/cli/main.py) 和 [`serve.py`](../../src/micro_eval/cli/serve.py) 都假设存在源码仓库中的 `ui/`，而 wheel 没有包含它。

这不是单纯的 UX 不好，而是安装后的公开命令无法兑现。

### 4. workspace 契约在文档中自相矛盾

权威 reference 说 `file_exists` 检查 workspace；但 example 文档又告诉用户 workspace 在验证前已经消失，必须写到 `MICRO_EVAL_OUTPUT_DIR`。

这说明当前不仅实现有问题，产品还没有最终决定：

> workspace 是可以验证和取证的执行产物，还是纯临时目录？

对于 micro-eval 的定位，答案应该是前者：先验证、取 diff、保存证据，最后 cleanup。

## 应该先完成的稳定化范围

我建议暂停 Quickstart、DSH 插件和新 UI，先只完成一个垂直切片：

```text
prepare workspace
→ invoke agent
→ collect workspace diff/artifacts
→ run deterministic validators
→ persist evidence/result
→ cleanup workspace
```

验收必须覆盖：

1. `blank`、`files`、`git_repo` 三类 workspace。
2. Agent 创建文件后，`file_exists` 能通过。
3. Agent 修改代码后，`command: pytest` 能在修改后的 workspace 运行。
4. Git diff 在 cleanup 前进入 Artifact/Evidence。
5. 所有验证和取证结束后 workspace 才被删除。
6. cleanup 失败只产生 caveat，不丢失已经生成的结果。
7. secret 出现在 diff、文件或 validator 输出时仍会被脱敏。
8. 这些测试必须经过真实 `ExecutionKernel`，不能只分别测试 validator 和 WorkspaceManager。

同时做一个产品边界决定：

- 要么当前 wheel 明确为 CLI-only，暂时不暴露 `ui`/`serve`；
- 要么把可运行的 UI 产物正式包含进安装包。

不能继续保持“命令存在，但只有源码 checkout 才能运行”的状态。

## 最终判断

**不用重新做 micro-eval，也不用先改变核心产品模型。**

需要的是先把以下范围封成一个可信的 `local-core`：

- 本地 CLI Agent
- blank/files/git workspace
- 四种 deterministic expectation
- workspace diff/artifact
- same-start
- evidence/decision
- 静态报告

这个范围稳定后，新的五分钟入口只是把用户意图编译成同一个 RunPlan，不再需要动核心行为。

所以正确顺序是：

```text
先修执行正确性与安装契约
→ 宣布 local-core stable
→ 再做五分钟入口
→ 最后接 DSH/Codex/Web 等入口 Adapter
```

现在直接做友好入口，会让用户更容易、更快地抵达一个可能错误的 workspace 评测结果。先完成这次稳定化，micro-eval 才真正有资格成为你设想中的强大基座。
