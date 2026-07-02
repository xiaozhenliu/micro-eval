---
title: "micro-eval 测试覆盖规划"
date: 2026-06-15
updated: 2026-07-02
status: completed
type: spec
tags:
  - testing
  - coverage
  - planning
---

# micro-eval 测试覆盖规划

> **状态注记（2026-07-02）**：本计划已执行完毕。基线为 v0.3.1（224 pytest + 48 vitest），当前规模为 517 pytest + 42 vitest（2026-07-02，v0.4.1）。保留本文档作为覆盖规划的历史参考。
>
> **基线**: v0.3.1, 224 pytest + 48 vitest, 整体覆盖率 78%。
>
> **目标**: 核心路径 ≥ 90%, 整体 ≥ 88%, 不追求 100%。
>
> **权威来源**: 测试架构见 `docs/superpowers/specs/2026-06-02-test-architecture.md`; 工程执行原则见 `docs/engineering/testing-guidelines.md`。本文档只管"补什么、按什么顺序补"。

---

## 1. 覆盖率现状快照

| 文件 | 语句数 | 覆盖率 | 未覆盖行数 | 备注 |
|------|--------|--------|-----------|------|
| `cli/{init,list,main,run,validate}.py` | ~415 | **0%** | 全部 | 仅通过 e2e 间接覆盖 |
| `engine/providers/remote.py` | 131 | **44%** | 74 | E2B/Modal, 无凭证 fail-hard |
| `evaluation/llm_judge.py` | 102 | **65%** | 36 | DeepEval client 封装路径 |
| `engine/providers/os_policy.py` | 96 | **69%** | 30 | Seatbelt/Bubblewrap 降级 |
| `decision/trend.py` | 38 | **71%** | 11 | `compute_all_trends` 主入口 |
| `engine/workspace.py` | 242 | **73%** | 66 | 多源 fixture + diff + snapshot |
| `trace/langfuse_provider.py` | 70 | **80%** | 14 | SDK 降级路径 |
| `engine/adapter.py` | 195 | **85%** | 30 | subprocess 异常分支 |
| `engine/providers/git_worktree.py` | 135 | **85%** | 20 | setup 命令分支 |
| `store/artifact_store.py` | 94 | **86%** | 13 | manifest 边界 |
| `config/loader.py` | 116 | **87%** | 15 | 错误路径 |
| `models/configuration.py` | 169 | **85%** | 25 | validator 分支 |

已达标文件（≥ 90%）从略：`kernel.py` 90%, `run_store.py` 95%, `sqlite_store.py` 93%, `aggregation.py` 97%, `summary.py` 95%, `validator.py` 94%, 全部 models 95%+ 等。

---

## 2. 价值排序原则

测试价值 ≠ 覆盖率缺口大小。排序依据：

1. **安全边界** — 沙箱策略、workspace 隔离、secrets redaction。未测 = 安全承诺无法验证。
2. **核心正确性** — 产品核心承诺（同起点可复现、趋势分析可信）的实现代码。
3. **用户入口** — CLI 参数解析 / 错误提示。静默回归 = 用户体验直接受损。
4. **回归防护** — 已有功能的边界条件，防止未来改动引入 regression。
5. **外部依赖封装** — DeepEval / Langfuse / E2B 等，mock 比例高，真实信号低，延后。

---

## 3. 分层规划

### Tier 1 — 必须补（核心正确性 + 安全）

#### 3.1 `engine/workspace.py` (73% → 目标 90%+)

**为什么重要**: workspace 是"同起点可复现"承诺的核心实现层。未覆盖的 66 行集中在 `copy_files` 多源路径、`collect_diff` 异常分支、`SameStartSnapshot` 构建逻辑——均为 Phase 3 关键交付物。

**测试方向**:

| 测试场景 | 覆盖目标行 | 测试类型 |
|----------|-----------|----------|
| `copy_files()` 多源 fixture 合并（file + git 混合） | L62-84 | unit |
| `collect_diff()` dirty worktree | L145-166 | unit |
| `collect_diff()` clean worktree（空 diff） | L179-183 | unit |
| `collect_diff()` non-git 目录降级 | L247-275 | unit |
| `SameStartSnapshot` toolchain fingerprint 计算 | L306-317 | unit |
| `SameStartSnapshot` fixture digest 比较（match / mismatch） | L349-406 | unit |
| `SameStartSnapshot` 跨 run 不兼容时产出 caveat | L376-393 | unit |
| workspace cleanup 失败时不抛异常 | L117-118 | unit |

**预估**: ~8-10 个测试用例, ~150 行。

**依赖**: conftest 中已有小型 fixture git repo 模式，可复用。

#### 3.2 `engine/providers/os_policy.py` (69% → 目标 85%+)

**为什么重要**: OS 沙箱策略是安全边界。Seatbelt(macOS) / Bubblewrap(Linux) 的策略生成和降级路径未验证 = 安全声明无依据。

**测试方向**:

| 测试场景 | 覆盖目标行 | 测试类型 |
|----------|-----------|----------|
| Seatbelt profile 生成（允许/拒绝路径正确性） | L101-114 | unit |
| Bubblewrap 命令构建（bind-mount 映射） | L142-199 | unit |
| 工具不可用时 Level 0 降级 + caveat 标记 | L214, L234-251 | unit |
| 平台检测（macOS → Seatbelt, Linux → Bubblewrap, 其他 → 降级） | L166-202 | unit |
| 策略文件写入 tmpdir 且 cleanup | L146-147 | unit |

**预估**: ~6-8 个测试用例, ~120 行。

**依赖**: mock `shutil.which` + `platform.system()`，无外部依赖。

#### 3.3 `decision/trend.py` (71% → 目标 95%+)

**为什么重要**: 趋势分析是用户直接面对的决策功能。仅 38 行代码、11 行未覆盖——**性价比最高的补测项**。

**测试方向**:

| 测试场景 | 覆盖目标行 | 测试类型 |
|----------|-----------|----------|
| `compute_all_trends()` 完整路径（多 metric × 多 configuration） | L79-105 | unit |
| drift breakpoint 标注（SameStartSnapshot 不兼容时插入断点） | L85-95 | unit |
| 空数据输入（0 个 run） | L79-80 | unit |
| 单点数据（1 个 run，无法计算趋势） | L82-85 | unit |

**预估**: ~4-5 个测试用例, ~60 行。

---

### Tier 2 — 应该补（用户入口 + 回归防护）

#### 3.4 CLI 集成测试 (0% → 目标基本覆盖)

**为什么重要**: CLI 是用户与 Python 引擎的唯一交互入口。0% 覆盖意味着参数解析、错误提示、输出格式完全没有自动化保护。

**策略**: 使用 Typer 的 `CliRunner.invoke()` 直接测试命令函数。不用 subprocess——快、无进程开销、可捕获 exit code 和 stdout。

**测试方向**:

| 命令 | 测试场景 | 测试类型 |
|------|----------|----------|
| `run` | 有效 config → 正常完成（mock kernel.execute） | integration |
| `run` | 无效 config → exit code 非零 + 有意义的错误信息 | integration |
| `run` | 缺失 config 文件 → 友好报错 | integration |
| `validate` | 合法 YAML → exit 0 + "valid" 提示 | integration |
| `validate` | 非法 YAML → exit 非零 + 校验错误详情 | integration |
| `list` | 有 run 目录 → 列出 run | integration |
| `list` | 无 run 目录 → 空结果 / 友好提示 | integration |
| `init` | 生成默认 config 文件到指定路径 | integration |
| `init` | 目标文件已存在 → 不覆盖 / 提示 | integration |
| `report` | 有效 run → HTML 输出 | integration |
| `report` | 无效 run ID → 友好报错 | integration |

**预估**: ~10-12 个测试用例, ~200 行。

**注意**: 需要 fixture 目录结构；mock `kernel.execute` 避免真实 agent 执行。

**新建文件**: `tests/integration/test_cli_commands.py`（现有 e2e 测试走完整流程，这里只测 CLI 层入口逻辑）。

#### 3.5 `config/loader.py` (87% → 目标 93%+)

**为什么重要**: 配置加载是所有 run 的前置步骤。15 行未覆盖集中在错误路径。

**测试方向**:

| 测试场景 | 覆盖目标行 |
|----------|-----------|
| 配置文件不存在 → FileNotFoundError | L82-83 |
| YAML 语法错误 → 有意义的解析错误 | L110-115 |
| schema 校验失败（缺失必填字段） → ValidationError | L155-158 |
| 环境变量引用解析 | L193-234 |

**预估**: ~4 个测试用例, ~50 行。

---

### Tier 3 — 可以补（提升信心，非阻塞）

#### 3.6 `engine/adapter.py` (85% → 目标 90%)

未覆盖行集中在 subprocess 错误处理分支（进程崩溃、超时中断、output 截断）。已有 `test_p0_cell_isolation.py` 覆盖主路径。

- 进程非零退出 + stderr 捕获
- 超时 kill 后的 cleanup
- output 超过 truncation limit
- **预估**: ~3-4 个测试, ~60 行

#### 3.7 `store/artifact_store.py` (86% → 目标 92%)

- manifest.json 损坏 / 不存在时的降级
- artifact 超过 50MB cap 时的拒绝
- **预估**: ~3 个测试, ~40 行

#### 3.8 `models/configuration.py` (85% → 目标 92%)

- 非法 AgentSpec（缺 command）
- repetition 边界值（0、负数、超大值）
- SkillSpec 路径校验
- **预估**: ~3 个测试, ~40 行

---

### 不补 / 延后

| 文件 | 覆盖率 | 理由 |
|------|--------|------|
| `providers/remote.py` | 44% | E2B/Modal 远程 provider。设计上无凭证时 fail-hard，mock 全部外部调用 = 测了个寂寞。**等真实使用场景出现再补** |
| `evaluation/llm_judge.py` | 65% | TODOS 已标 Blocked。缺口在 DeepEval client 封装路径，**等生产链路启用后补** |
| `trace/langfuse_provider.py` | 80% | SDK 降级路径依赖外部 SDK payload 形状。**pin 版本 + 被动维护** |

---

## 4. 实施批次

| 批次 | 内容 | 预估测试数 | 预估代码量 | 覆盖率提升 |
|------|------|-----------|-----------|-----------|
| **Batch 1** | trend.py + workspace.py + os_policy.py | ~20 | ~330 行 | 78% → ~83% |
| **Batch 2** | CLI 集成测试 | ~12 | ~200 行 | ~83% → ~87% |
| **Batch 3** | loader + adapter + artifact_store + configuration | ~13 | ~160 行 | ~87% → ~90% |

### 批次内优先级

**Batch 1 内部顺序**: trend.py（热身，半小时可完成）→ workspace.py（核心，工作量最大）→ os_policy.py（安全，需 mock）。

**Batch 2**: 单独一批是因为 CLI 测试需要搭建 fixture 目录 + CliRunner 基础设施，有固定成本；一旦搭好，12 个用例可快速铺开。

**Batch 3**: 各文件独立、缺口小，可并行补。

---

## 5. 新增测试文件规划

| 文件路径 | 覆盖模块 | 批次 |
|----------|----------|------|
| `tests/unit/test_workspace_snapshot.py` | workspace.py 的 SameStartSnapshot 路径 | Batch 1 |
| `tests/unit/test_workspace_diff.py` | workspace.py 的 collect_diff 路径 | Batch 1 |
| `tests/unit/test_trend_compute.py` | decision/trend.py | Batch 1 |
| `tests/unit/test_os_policy_provider.py` | 已存在，追加用例 | Batch 1 |
| `tests/integration/test_cli_commands.py` | cli/*.py | Batch 2 |
| `tests/unit/test_config_loader.py` | 已存在，追加用例 | Batch 3 |

已存在的测试文件（`test_os_policy_provider.py`, `test_config_loader.py` 等）在现有文件中追加用例，不新建。

---

## 6. 验收标准

- [ ] Batch 1 完成后：`decision/trend.py` ≥ 95%, `engine/workspace.py` ≥ 90%, `engine/providers/os_policy.py` ≥ 85%
- [ ] Batch 2 完成后：`cli/` 模块有基本覆盖（每个命令至少 happy path + error path）
- [ ] Batch 3 完成后：整体覆盖率 ≥ 88%
- [ ] 全部新增测试无 flaky（不调用真实 LLM、不依赖外网、时间可控）
- [ ] 全部新增测试在 CI 中 < 10s 完成（单个文件级别）
