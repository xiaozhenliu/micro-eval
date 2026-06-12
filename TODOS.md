# TODOS.md

## 当前待办（2026-06-12 整理，v0.2.2 发布后）

### Phase 3 设计文档（下一个里程碑）
**What:** Docker sandbox + 更复杂 workspace 类型 + 趋势分析的实施计划。
**Why:** CLAUDE.md 路线图的 Phase 3；执行链路改动安全敏感度高（网络边界、容器逃逸面、凭证传递）。
**How:** 沿用 Phase 2 计划格式（`docs/superpowers/plans/`），动工前过 security-guidelines 评审。两个 P0 测试防线（跨语言契约、黄金路径 e2e）已就位作为回归保障。

### cli/report.py 渲染契约测试
**What:** 文本/HTML 报表渲染分支补契约测试（当前行覆盖 32%）。
**Why:** 报表是用户决策界面；至少 pass@k 列与 caveat 渲染应有契约保护。
**Priority:** P2。

### llm_judge DeepEval client 封装测试
**What:** `evaluation/llm_judge.py` 中 DeepEval client 与 score 解析分支补测（当前 64% 覆盖，缺的是外部依赖路径）。
**Why:** judge 真实启用后该路径进入生产链路。
**Depends on:** judge 真实使用场景出现。

### 本地残留分支清理
**What:** 清理 `codex/bench-*` 与 `worktree-wf_*` 本地分支（若已无用）。
**Priority:** 顺手项。

## GitHub Issues 开放项（2026-06-12 核实，详情见各 issue）

代码级核实后的状态：#7、#11 已解决并关闭；以下 12 个仍开放，按风险排序。

### 正确性 bug（建议最优先）
- **#13** `file_exists`/`command` expectations 验证的是 artifact 目录而非 agent 实际执行的 workspace——git_repo/files 工作区下验证看不到 agent 的改动（`kernel.py` 传 `artifact_store.cell_dir` 给 `validate_cell`）。
- **#14** kernel 只捕获 `WorkspaceError`/`AdapterError`；validation/store 等其他异常会中止整个 run，应扩大 per-cell 隔离实现优雅的部分完成。

### 安全/边界
- **#10** `git_repo` workspace 的 source path 未限制在 project root 内（接受任意绝对路径）。

### 双端一致性
- **#1** UI `recomputeDecision` 手工镜像 Python `build_decision` 算法（denominator_policy 修复时双端各改一遍即此风险实证）；golden 契约只保护 schema 形状不保护算法等价。
- **#6** zod `EvaluationResult` 缺 Python 端强制的 pass_fail → evidence_refs 校验（schema.ts 无 refine）。
- **#12** 二进制内容检测阈值不统一：adapter 检查全文 `\x00`，artifact store 只看前 1024 字节。

### 契约测试缺口（#5，部分完成）
- exec-not-shell 已由 CI grep 门禁兜底（v0.2.2）；仍缺 kernel-must-use-adapter 与 timeout→terminate→kill 隔离两条契约测试。

### 规格一致性与遗留清理
- **#9** 小型 spec 偏差清单：默认 concurrency 2 vs spec 4、trace_id 格式、truncation flag 未持久化、artifact cap、错误分类命名、schema 字段超出文档模型、redactor 命名（spec 先行规则：部分项应先改权威 spec）。
- **#8**（部分完成）validator 路径不写 `rubric_hash`（judge 路径已写）。
- **#2** configuration 内容变化但 id 不变时缺少跨 run 可比性警告。
- **#3** 退役不可达的 legacy 执行/评分模块（`models/schema.py`、`engine/scorer.py`；`test_full_flow.py` 仍依赖）。
- **#4** 迁移 legacy run.json 读取路径，使 legacy schema 模块可退役（`list_runs` flat JSON fallback）。

### 来自 #7 关闭时的剩余项
- AdapterResult/CellResult 增加 agent 自报 cost 字段（cost ladder 第 2 级），等真实 agent 上报 cost 的用例。

## Phase 2+ 遗留（来自工程评审 2026-05-31，仍然开放的部分）

### Run ordering 随机化
**What:** 随机化 baseline/candidate 的执行顺序，并记录到 Run JSON 中。
**Why:** 避免顺序效应偏差。并行执行已缓解大部分问题，但串行模式或 >2 agent 对比时变得重要。
**Status:** 未实施（代码中无 ordering 随机化）。

### Task 模型增强（剩余部分）
**What:** allowed files 白名单与 diff expectations。
**Why:** 限制 agent 可改动范围并对 diff 本身做断言。
**Status:** 大部分已交付——WorkspaceSpec（git_repo/files/setup）、ExpectationSpec（exit_code/contains/file_exists/command）、`collect_diff` 产出 patch artifact 均已实现（v0.1.x–v0.2.x）。仅剩 allowed-files 与 diff 断言两项，等真实用例。

### Concurrency control（剩余部分）
**What:** 全局超时、取消机制、断点恢复。
**Why:** Agent 评测慢且贵。
**Status:** `--max-concurrency`（CLI + guardrails）、per-cell timeout、`stop_on_cell_error` 已交付。全局超时/取消/断点恢复未实施，等实际使用反馈。

### JSON → SQLite 迁移路径
**What:** run 数量增长后从 JSON 文件迁移到 SQLite。
**Status:** 未实施。`schema_version` 字段已为迁移预留；触发条件（跨 run 查询需求）尚未出现。

## 已解决（留档）

- **Secret redaction**（2026-05-31 评审项）——已交付：`Redactor` + `MICRO_EVAL_SECRET_*` 通道覆盖 artifact/evidence/judge prompt/trace summary/validator 输出，含否定测试（v0.1.x–v0.2.1）。
- **output_mode: directory 评分机制**（2026-05-31 评审项）——已交付：adapter 支持 directory 输出收集，评分经 task-specific expectations（file_exists/command validators）实现。
