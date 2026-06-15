---
title: Example Coverage Completion Plan
codename: example_showcase.v1
status: implemented
author: micro-eval
date: 2026-06-15
authority: docs/superpowers/specs/2026-06-02-unicorn-design.md (Part I §5), CLAUDE.md
---

# Example Coverage Completion Plan: `example_showcase.v1`

> 当前 `examples/agent-codefix-showdown/` 覆盖了约 50% 的项目能力。本计划补足剩余能力的示例展示，使新用户通过 example 即可体验 micro-eval 的全部已交付功能。

## 0. 现状与问题

### 现有 example 覆盖

| 能力 | 覆盖 |
|------|------|
| 矩阵执行 (Tasks × Configs × Reps) | ✓ |
| `files` workspace | ✓ |
| `contains` expectation | ✓ |
| `stdin` input / `file` output | ✓ |
| argv-only 安全执行 | ✓ |
| per-cell timeout / guardrails | ✓ |
| process trace | ✓ |
| pass@k / pass^k 聚合 | ✓ |
| decision.json + 自动决策 | ✓ |
| CLI 全流程 (validate→run→list→report) | ✓ |
| Web UI 查看 | ✓ |
| rubric / EvaluationContract | ✓ |
| baseline/candidate role | ✓ |

### 未覆盖的缺口（按用户感知影响排序）

| # | 缺口 | 影响 | 所属 Phase |
|---|------|------|-----------|
| G1 | `git_repo` workspace + git worktree 隔离 | **高** — 产品定位核心（同起点可复现），用户无法体验最核心的隔离机制 | P1 |
| G2 | 多 task 矩阵 (N×M) | **高** — 当前 1 task 看不到矩阵展开效果 | P1 |
| G3 | `exit_code` / `file_exists` / `command` expectation | **中** — 四种验证器只展示了一种 | P1 |
| G4 | `stdout` / `directory` output mode | **中** — 三种输出模式只展示了一种 | P1 |
| G5 | OS 策略沙箱 (Seatbelt/Bubblewrap) | **中** — Phase 3 核心交付无体验入口 | P3 |
| G6 | 多源 fixture + toolchain fingerprint | **中** — Phase 3-d 交付无展示 | P3 |
| G7 | 趋势分析（跨 run 对比 + drift breakpoint） | **中** — Phase 3-e 交付无展示 | P3 |
| G8 | LLM Judge（补充评分） | **低** — 配置已有但 disabled，需 API key | P2 |
| G9 | Langfuse trace | **低** — 需外部服务，体验门槛高 | P2 |
| G10 | 人工标注流程引导 | **低** — UI 组件已有但 README 未引导 | P2 |
| G11 | secrets 通道 (`MICRO_EVAL_SECRET_*`) | **低** — 安全特性，不易做离线 demo | P1 |
| G12 | `setup` commands (workspace 初始化脚本) | **低** — 数据模型支持但未使用 | P1 |
| G13 | caveat 系统的真实触发 | **中** — mock 全通过，看不到 caveat 降级效果 | P1 |

## 1. 设计原则

1. **新 example 独立于现有 example** — 不修改 `agent-codefix-showdown`，新增独立 example 目录。现有 example 作为"快速入门"保留，新 example 作为"能力全景"补充。
2. **离线可跑优先** — 每个 example 必须有 mock/deterministic 路径，不依赖 API key 或外部服务。需要外部依赖的能力（LLM Judge、Langfuse、E2B/Modal）提供配置模板 + 文档说明，但不作为默认路径。
3. **一个 example 覆盖多个缺口** — 不为每个缺口单独建 example，而是设计有业务含义的场景，自然覆盖多个能力点。
4. **渐进体验** — example 之间有推荐顺序：快速入门 → 核心能力 → 高级特性。
5. **与 `run-example.py` 统一入口风格** — 每个新 example 也提供一键运行脚本。

## 2. Example 规划

### 总览

```
examples/
├── run-example.py                      # 现有：一键入口（默认跑 agent-codefix-showdown）
├── agent-codefix-showdown/             # 现有：快速入门（保持不变）
├── multi-task-matrix/                  # 新增 E1：多 task 矩阵 + 全部验证器 + 多输出模式
├── git-workspace-isolation/            # 新增 E2：git_repo workspace + 沙箱 + 趋势分析
└── README.md                           # 更新：加入能力覆盖索引
```

### E1: `multi-task-matrix` — 多任务矩阵全景

**场景**：评测两个"代码质量检查 agent"在三个不同任务上的表现矩阵。mock agent 之一故意在部分 task 上失败，触发 caveat 和 mixed 决策。

**覆盖缺口**：G2（多 task）、G3（全部 expectation 类型）、G4（stdout + directory output）、G12（setup commands）、G13（caveat 真实触发）。

#### 文件结构

```
multi-task-matrix/
├── run.py                          # 一键运行脚本
├── eval.mock.yaml                  # 2 configs × 3 tasks × 2 reps = 12 cells
├── tasks/
│   ├── check-style.yaml            # Task 1: 检查代码风格 → exit_code expectation
│   ├── find-bugs.yaml              # Task 2: 查找 bug → contains + file_exists expectation
│   └── generate-report.yaml        # Task 3: 生成报告目录 → command expectation + directory output
├── workspace/
│   ├── sample-project/
│   │   ├── main.py                 # 待检查的样本代码（有风格问题 + 隐藏 bug）
│   │   ├── utils.py
│   │   └── tests/test_main.py
│   └── scripts/
│       ├── mock-good-checker.py    # mock agent A: 全部正确完成
│       └── mock-flaky-checker.py   # mock agent B: task 1,2 通过但 task 3 失败
└── README.md
```

#### 配置设计要点

```yaml
# eval.mock.yaml 关键结构
configurations:
  - id: checker-alpha
    name: Style Checker Alpha
    role: baseline
    repetitions: 2
    agent:
      command: ["{python}", "workspace/scripts/mock-good-checker.py", "{output_file}"]
      input_mode: stdin
      output_mode: file        # Task 1,2 用 file output
      timeout_s: 30

  - id: checker-beta
    name: Style Checker Beta
    role: candidate
    repetitions: 2
    agent:
      command: ["{python}", "workspace/scripts/mock-flaky-checker.py", "{output_file}"]
      input_mode: stdin
      output_mode: file
      timeout_s: 30

tasks:
  - tasks/check-style.yaml          # exit_code expectation
  - tasks/find-bugs.yaml            # contains + file_exists
  - tasks/generate-report.yaml      # command expectation
```

#### Task 设计

**Task 1: check-style** — 展示 `exit_code` expectation
```yaml
expectations:
  - type: exit_code
    value: 0
workspace:
  type: files
  files: [sample-project]
  setup:                            # 覆盖 G12: setup commands
    - ["{python}", "-m", "py_compile", "main.py"]
```

**Task 2: find-bugs** — 展示 `contains` + `file_exists` expectation
```yaml
expectations:
  - type: contains
    stream: output
    value: "BUG_FOUND"
  - type: file_exists
    path: "bugs-report.txt"         # agent 需要产出这个文件
```

**Task 3: generate-report** — 展示 `command` expectation + `directory` output mode（此 task 在配置中 override output_mode）
```yaml
expectations:
  - type: command
    argv: ["{python}", "-c", "import json; json.load(open('report/summary.json'))"]
    timeout_s: 10
workspace:
  type: files
  files: [sample-project]
```

#### mock agent 行为设计

- **mock-good-checker.py**：三个 task 全部正确完成，产出期望的文件和输出。
- **mock-flaky-checker.py**：task 1、2 正确，task 3 故意不生成 `report/summary.json`，导致 command expectation 失败。

这样产出的 decision 是 `mixed`（baseline 全 pass，candidate 部分 fail），用户可以直观看到：
- 2×3 矩阵的展开效果
- caveat 系统（candidate 在 task 3 失败触发 caveat）
- `mixed` 决策状态（非全赢全输）
- 四种 expectation 类型的实际运作

#### stdout output mode 展示

Task 1（check-style）的 mock agent 使用 stdout 输出模式。在 eval.mock.yaml 中为这个 task 的 configuration 设置 `output_mode: stdout`，与 Task 2/3 的 file 模式形成对比。

具体方式：configurations 中用两套 agent command，一套走 stdout，一套走 file，或者用同一个 mock script 根据环境变量切换。更简洁的做法：mock-good-checker 读取 task id 后，对 check-style task 直接 print 到 stdout 而非写文件，在 eval.mock.yaml 中对该 task 用单独的 configuration variant。

> 设计权衡：为保持 YAML 简洁和新用户可读性，**不在此 example 中为 stdout/directory 各开一个 configuration**。改为在 README 中用 diff 展示"如何把 file output 改为 stdout output"和"如何使用 directory output"，附带可直接粘贴的 YAML 片段。这避免 config 数量爆炸（2 config × 3 task × 2 rep = 12 cell 已足够展示矩阵），同时覆盖文档层面的 G4。

### E2: `git-workspace-isolation` — Git 隔离 + 沙箱 + 趋势

**场景**：评测一个 agent 对 git 仓库中 Python 文件的重构能力。用 `git_repo` workspace，每个 cell 在独立 git worktree 中执行。通过两次 run（修改 config 后再跑）展示趋势分析和 drift breakpoint。

**覆盖缺口**：G1（git_repo workspace）、G5（OS 策略沙箱）、G6（多源 fixture + toolchain）、G7（趋势分析）、G10（人工标注引导）、G13（drift caveat）。

#### 前置条件

这个 example 需要在一个 git repo 内运行。方案：example 自带一个 `fixture-repo/` 目录，`run.py` 启动时自动 `git init` + 初始提交，作为被测 workspace 的 git_repo 源。

#### 文件结构

```
git-workspace-isolation/
├── run.py                          # 一键运行（含 git init fixture + 两次 run + 趋势查看）
├── eval.mock.yaml                  # 基础配置：git_repo workspace
├── eval.mock.v2.yaml               # 变体配置：修改 agent 参数（触发 drift）
├── tasks/
│   ├── refactor-extract-function.yaml    # 从大函数中提取子函数
│   └── add-type-hints.yaml               # 给函数添加类型标注
├── fixture-repo/                   # 会被 run.py 初始化为 git repo
│   ├── app.py                      # 待重构的代码（大函数 + 无类型标注）
│   ├── requirements.txt            # toolchain fingerprint 来源
│   └── tests/test_app.py
├── scripts/
│   ├── mock-refactor-agent.py      # mock agent: 执行重构
│   └── mock-typehint-agent.py      # mock agent: 添加类型标注
└── README.md
```

#### 配置设计要点

```yaml
# eval.mock.yaml
configurations:
  - id: refactor-agent-v1
    name: Refactor Agent v1
    role: baseline
    repetitions: 2
    agent:
      command: ["{python}", "scripts/mock-refactor-agent.py"]
      input_mode: stdin
      output_mode: stdout           # 展示 stdout output mode
      timeout_s: 60

tasks:
  - tasks/refactor-extract-function.yaml
  - tasks/add-type-hints.yaml

# git_repo workspace — 覆盖 G1
# task 中的 workspace spec:
#   type: git_repo
#   path: fixture-repo
#   ref: HEAD
#   fixtures:
#     - path: fixture-repo
#       digest: <auto>              # 覆盖 G6: fixture digest
#   toolchain:
#     runtime: python3
#     lockfile: requirements.txt    # 覆盖 G6: toolchain fingerprint
```

#### OS 策略沙箱展示 (G5)

```yaml
# eval.mock.yaml 中的 workspace spec
workspace:
  type: git_repo
  path: fixture-repo
  isolation_level: os_policy        # 请求 Seatbelt/Bubblewrap 隔离
  trust_level: semi_trusted
  network_policy: none              # 禁止网络访问
```

运行时行为：
- macOS 上：Seatbelt provider 生效，agent 进程在沙箱中运行
- Linux 上：Bubblewrap provider 生效
- 两者均不可用时：降级到 Level 0 (logical) + 记录 caveat

README 中说明观察点：run.json 的 `same_start_snapshot.sandbox_policy` 记录了实际使用的隔离级别，caveat 中会标注降级信息。

#### 趋势分析展示 (G7)

`run.py` 自动化以下流程：

```
Step 1: 用 eval.mock.yaml 跑第一次 run
Step 2: 用 eval.mock.v2.yaml 跑第二次 run（agent 参数变化 → config digest 变化）
Step 3: 启动 UI，引导用户查看 /api/trends 和趋势页
Step 4: 说明 drift breakpoint（两次 run 之间 config 变化产生不可比标注）
```

`eval.mock.v2.yaml` 与 `eval.mock.yaml` 的差异仅为 agent timeout 或 env 参数变化，足以触发 config drift caveat，使趋势图上出现 breakpoint 标注。

#### 人工标注引导 (G10)

README 中加入明确步骤：

```
1. 跑完 run 后启动 UI：python run.py --ui
2. 打开 http://localhost:3000/run/{run_id}
3. 在 AnnotationPanel 中为任意 cell 添加人工评分和评论
4. 刷新页面，确认标注已持久化到 evaluation.json
5. 重新生成报告：micro-eval report --format text — 观察人工标注出现在报告中
```

### LLM Judge / Langfuse / Secrets 的处理 (G8, G9, G11)

这三项**不单独建 example**，原因：
- 它们依赖外部 API key / 服务，无法做离线 mock 路径
- 配置方式简单（在现有 YAML 中改几行），不值得整个 example

处理方式：在 `examples/README.md` 中新增 **"Advanced: 可选外部集成"** 小节，提供可直接粘贴的 YAML 片段和步骤说明：

```markdown
### LLM Judge (DeepEval)
在任意 eval.yaml 中启用：
​```yaml
judge:
  enabled: true
  provider: deepeval
  model: "gpt-4o"
  temperature: 0.0
  pass_threshold: 0.5
  required_secrets: [MICRO_EVAL_SECRET_OPENAI_KEY]
​```
需设置环境变量：`export MICRO_EVAL_SECRET_OPENAI_KEY=sk-...`

### Langfuse Trace
​```yaml
trace:
  enabled: true
  provider: langfuse
​```
需设置：`LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST`

### Secrets 通道
声明在 agent 的 required_secrets 中，micro-eval 从 `MICRO_EVAL_SECRET_*` 环境变量注入，全链路 redaction。
```

### E2B/Modal 远程 Provider 的处理 (G5 补充)

同样不单独建 example（需云端凭证），在 `examples/README.md` 的 Advanced 小节说明配置方式：

```yaml
workspace:
  type: git_repo
  path: fixture-repo
  isolation_level: vm              # 请求远程 VM 隔离
  trust_level: untrusted
```

需设置 `E2B_API_KEY` 或 `MODAL_TOKEN_ID` + `MODAL_TOKEN_SECRET`。

## 3. 实施计划

### 里程碑 M1: `multi-task-matrix` example

**文件清单**：
- `examples/multi-task-matrix/run.py`
- `examples/multi-task-matrix/eval.mock.yaml`
- `examples/multi-task-matrix/tasks/check-style.yaml`
- `examples/multi-task-matrix/tasks/find-bugs.yaml`
- `examples/multi-task-matrix/tasks/generate-report.yaml`
- `examples/multi-task-matrix/workspace/sample-project/main.py`
- `examples/multi-task-matrix/workspace/sample-project/utils.py`
- `examples/multi-task-matrix/workspace/sample-project/tests/test_main.py`
- `examples/multi-task-matrix/workspace/scripts/mock-good-checker.py`
- `examples/multi-task-matrix/workspace/scripts/mock-flaky-checker.py`
- `examples/multi-task-matrix/README.md`

**核心契约**：
1. `python examples/multi-task-matrix/run.py` 零依赖完成，产出 2×3 矩阵结果
2. decision.json 的 verdict 为 `inconclusive`（baseline 全 pass vs candidate 部分 fail，decision 引擎不产出 `mixed`）
3. 至少使用 `exit_code`、`contains`、`file_exists`、`command` 四种 expectation 各一次
4. candidate 部分 task 失败在矩阵中可见（caveats 仅由 comparability/snapshot 问题触发，不由 validation 失败触发）
5. workspace 使用 `setup` commands

**验收标准**：
- `python examples/multi-task-matrix/run.py` exit 0
- `.micro-eval/runs/` 下产出完整 run.json + decision.json
- `report.html` 可在浏览器中查看，矩阵展示 2 configs × 3 tasks
- CI smoke 通过（如接入）

### 里程碑 M2: `git-workspace-isolation` example

**文件清单**：
- `examples/git-workspace-isolation/run.py`
- `examples/git-workspace-isolation/eval.mock.yaml`
- `examples/git-workspace-isolation/eval.mock.v2.yaml`
- `examples/git-workspace-isolation/tasks/refactor-extract-function.yaml`
- `examples/git-workspace-isolation/tasks/add-type-hints.yaml`
- `examples/git-workspace-isolation/fixture-repo/app.py`
- `examples/git-workspace-isolation/fixture-repo/requirements.txt`
- `examples/git-workspace-isolation/fixture-repo/tests/test_app.py`
- `examples/git-workspace-isolation/fixture-repo/scripts/mock-refactor-agent.py`
- `examples/git-workspace-isolation/fixture-repo/scripts/mock-typehint-agent.py`
- `examples/git-workspace-isolation/fixture-repo/.gitignore`
- `examples/git-workspace-isolation/README.md`

**核心契约**：
1. `python examples/git-workspace-isolation/run.py` 自动初始化 fixture git repo + 执行 run
2. workspace 使用 `git_repo` 类型，每个 cell 在独立 git worktree 中运行
3. SameStartSnapshot 包含 `fixture_digests` 和 `toolchain_fingerprint`
4. 第二次 run（v2 config）产生 config drift caveat
5. 趋势 API 返回两个 run 的对比数据，包含 drift breakpoint

**验收标准**：
- `python examples/git-workspace-isolation/run.py` exit 0
- run.json 中 `same_start_snapshot` 包含 sandbox_policy、fixture digest、toolchain fingerprint
- 两次 run 后，趋势 API 返回数据（手动 curl 或 `--ui` 查看）
- 如果 Seatbelt/Bubblewrap 可用，snapshot 中记录 `os_policy` 级别；否则 caveat 中标注降级

**前置条件验证**：
- `run.py` 在启动时检查 `git` 是否可用，不可用则 exit with 明确错误信息
- fixture-repo 的 `.gitignore` 应排除 `.micro-eval/`，避免 worktree 创建冲突

### 里程碑 M3: 文档更新

**文件清单**：
- `examples/README.md` — 更新：加入三个 example 的能力覆盖矩阵 + Advanced 外部集成小节
- `examples/run-example.py` — 更新：支持 `--example <name>` 参数选择 example

**README 能力覆盖矩阵**：

```markdown
| 能力 | codefix-showdown | multi-task-matrix | git-workspace-isolation |
|------|:---:|:---:|:---:|
| 矩阵执行 | ✓ | ✓ | ✓ |
| 多 task | | ✓ | ✓ |
| files workspace | ✓ | ✓ | |
| git_repo workspace | | | ✓ |
| exit_code expectation | | ✓ | |
| contains expectation | ✓ | ✓ | |
| file_exists expectation | | ✓ | |
| command expectation | | ✓ | |
| stdout output | | docs | ✓ |
| file output | ✓ | ✓ | |
| directory output | | docs | |
| setup commands | | ✓ | |
| process trace | ✓ | | |
| OS 策略沙箱 | | | ✓ |
| fixture digest | | | ✓ |
| toolchain fingerprint | | | ✓ |
| 趋势分析 + drift | | | ✓ |
| pass@k / pass^k | ✓ | ✓ | ✓ |
| caveat 真实触发 | | ✓ | ✓ |
| 人工标注引导 | | | ✓ (README) |
| LLM Judge | | | docs |
| Langfuse trace | | | docs |
| secrets 通道 | | | docs |
| E2B/Modal 远程 | | | docs |
```

`docs` = README 中提供配置片段和步骤说明，非 mock 可跑路径。

### `run-example.py` 统一入口更新

```python
# 新增 --example 参数
python examples/run-example.py                              # 默认：agent-codefix-showdown
python examples/run-example.py --example multi-task-matrix   # E1
python examples/run-example.py --example git-workspace-isolation  # E2
python examples/run-example.py --example all                # 按顺序跑全部
```

## 4. 实施顺序与依赖

```
M1 (multi-task-matrix)     ──┐
                              ├──→ M3 (文档更新)
M2 (git-workspace-isolation) ┘
```

M1 和 M2 无依赖关系，可并行实施。M3 在两者完成后更新文档。

**M1 预计工作量**：中等。需要设计 sample-project 代码、3 个 task YAML、2 个 mock agent 脚本、run.py、README。核心难点在 mock-flaky-checker 的行为设计——需要根据 task prompt 区分不同任务并有选择地失败。

**M2 预计工作量**：较大。需要设计 fixture git repo、处理 git init 自动化、git_repo workspace 的配置调试、两次 run 的趋势分析验证、OS 策略沙箱的可用性检测与降级说明。

**建议交付顺序**：M1 → M2 → M3（串行，M1 较简单先交付验证流程）。

## 5. 覆盖度提升预期

完成后的覆盖度：

| 维度 | 完成前 | 完成后 |
|------|--------|--------|
| Workspace 类型 (blank/files/git_repo) | 1/3 | 2/3 (blank 无独立 example，但 git_repo + files 覆盖核心场景) |
| Expectation 类型 | 1/4 | 4/4 |
| Output mode | 1/3 | 2/3 (directory 仅文档) |
| Phase 1 能力 | ~70% | ~95% |
| Phase 2 能力 | ~60% | ~80% (Judge/Langfuse 仅文档) |
| Phase 3 能力 | ~0% | ~70% (E2B/Modal 仅文档) |
| **整体** | **~50%** | **~85%** |

剩余 15% 为依赖外部服务的能力（LLM Judge、Langfuse、E2B/Modal），通过文档片段覆盖，无法做离线 mock。

## 6. 明确不含

- 不修改现有 `agent-codefix-showdown` example 的任何文件
- 不为 LLM Judge / Langfuse / E2B / Modal 创建独立 example（需外部凭证，提供文档片段）
- 不引入新的 Python 依赖（mock agent 仅使用标准库）
- 不改变项目的 CI pipeline（新 example 的 CI 集成如需要可后续跟进）
- 不创建 `blank` workspace 的独立 example（场景过于简单，无独立演示价值）
