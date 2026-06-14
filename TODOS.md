# TODOS.md

> **格式约定**（整理时遵守）：
> - 状态只有两种分组：**Ready**（已核实、可动手，按优先级排）/ **Blocked**（必填解除条件，整理时机械检查是否可移入 Ready）。
> - 优先级标尺：**P0** 正确性 bug 与里程碑 / **P1** 安全、双端一致性 / **P2** 质量、测试、重构 / **P3** 顺手项。
> - **有 GitHub issue 的事项只留一行指针**（编号 + 一句话 + 标签），详情以 issue 为权威，避免双源漂移。
> - **无 issue 的事项必须展开**：待做事项 + 关联文件，信息密度达到"新会话不靠考古就能动手"。
> - 完成项一行留档进 Done，定期清入 CHANGELOG 后删除。
>
> 最近整理：2026-06-14（v0.2.5 发布后；#13、#14、#10、#1、#6、#12 已交付并移入 Done）。

## Ready

### P0
- **Phase 3 设计文档**（里程碑，下一个动手项）
  - **待做:** Docker sandbox + 更复杂 workspace 类型 + 趋势分析的实施计划，沿用 Phase 2 计划格式（`docs/superpowers/plans/`）。
  - **注意:** 执行链路改动安全敏感度高（网络边界、容器逃逸面、凭证传递），动工前过 `docs/engineering/security-guidelines.md` 评审。两个 P0 测试防线（跨语言契约、黄金路径 e2e）已就位作为回归保障。

### P1
- **#5**（部分完成）剩余两条契约测试：kernel-must-use-adapter、timeout→terminate→kill 升级链；exec-not-shell 已由 CI grep 门禁兜底（v0.2.2）

### P2
- **#9** 小型 spec 偏差清单：默认 concurrency 2 vs spec 4、trace_id 格式、truncation flag 未持久化、artifact cap、错误分类命名、schema 字段超出文档模型、redactor 命名（spec 先行：部分项应先改权威 spec）
- **#8**（部分完成）validator 路径补写 `rubric_hash`（judge 路径已写）
- **#2** configuration 内容变化但 id 不变时缺少跨 run 可比性警告
- **#3** 退役不可达的 legacy 执行/评分模块（`models/schema.py`、`engine/scorer.py`；`test_full_flow.py` 仍依赖）
- **#4** 迁移 legacy run.json 读取路径（`list_runs` flat JSON fallback），使 legacy schema 模块可退役
- **cli/report.py 渲染契约测试**（无 issue）
  - **待做:** 文本/HTML 报表渲染分支补契约测试，至少覆盖 pass@k 列与 caveat 渲染。
  - **关联文件:** `src/micro_eval/cli/report.py`（当前行覆盖 32%）。
  - **Why:** 报表是用户决策界面，渲染回归直接误导结论。

### P3
- **本地残留分支清理**（无 issue）
  - **待做:** 确认无用后删除 `codex/bench-*` 与 `worktree-wf_*` 本地分支。
- **Run ordering 随机化**（无 issue，来自 2026-05-31 工程评审）
  - **待做:** 随机化 baseline/candidate 的执行顺序，并把 ordering 记录到 Run JSON。
  - **关联文件:** `src/micro_eval/engine/kernel.py`、`src/micro_eval/models/run.py`。
  - **Why:** 避免顺序效应偏差；并行执行已缓解大部分问题，串行模式或 >2 agent 对比时才重要。

## Blocked

### llm_judge DeepEval client 封装测试
- **解除条件:** LLM judge 进入真实生产链路（有用户实际启用 judge 评分）。
- **关联文件:** `src/micro_eval/evaluation/llm_judge.py`（当前覆盖 64%）。
- **待做:** 补 DeepEval client 封装与 score 解析分支的测试——缺口集中在外部依赖路径（client 初始化失败、API 返回异常 score、解析降级）。需 mock DeepEval client。

### Task 模型增强：allowed-files 白名单 + diff expectations
- **解除条件:** 出现需要限制 agent 改动范围或对 diff 做断言的真实任务用例。
- **关联文件:** `src/micro_eval/models/task.py`（ExpectationSpec）、`src/micro_eval/evaluation/validator.py`、`src/micro_eval/engine/workspace.py`（`collect_diff` 已产出 patch artifact，可作为断言输入）。
- **待做:** ① Task 模型加 allowed_files 字段 + validator 校验 diff 是否越界；② 新增 diff 类 expectation（对 patch 内容断言）。schema 改动需同步 ui 端 zod 与 contract golden。
- **已交付部分（v0.1.x–v0.2.x）:** WorkspaceSpec（git_repo/files/setup）、ExpectationSpec（exit_code/contains/file_exists/command）、`collect_diff` patch artifact。

### Agent 自报 cost 字段（#7 关闭时剩余项）
- **解除条件:** 出现会上报 cost 的真实 agent（cost ladder 第 2 级）。
- **关联文件:** `src/micro_eval/engine/adapter.py`（AdapterResult）、`src/micro_eval/models/run.py`（CellResult）、contract golden（`scripts/generate-golden.py`）。
- **待做:** AdapterResult/CellResult 增加 agent 自报 cost 字段，约定上报格式（stdout 标记或文件），与 Langfuse cost 的优先级关系写入 spec。

### Run 级全局超时 / 取消 / 断点恢复
- **解除条件:** 实际使用中出现长 run 被迫整体重跑的反馈。
- **关联文件:** `src/micro_eval/engine/kernel.py`、`src/micro_eval/engine/runner.py`、`src/micro_eval/cli/`。
- **待做:** ① run 级 wall-clock 超时；② SIGINT 优雅取消（已完成 cell 落盘）；③ 断点恢复（跳过已有结果的 cell 重跑剩余矩阵）。三项可独立交付，断点恢复依赖 run_store 的 cell 级幂等写入。
- **已交付部分:** `--max-concurrency`（CLI + guardrails）、per-cell timeout、`stop_on_cell_error`。

### JSON 文件存储 → SQLite 迁移
- **解除条件:** 出现跨 run 查询需求（趋势分析、Phase 3 触发）。
- **关联文件:** `src/micro_eval/store/run_store.py`、`src/micro_eval/store/artifact_store.py`、ui API routes（直接读 `.micro-eval/` JSON）。
- **待做:** schema_version 字段已预留；迁移时需同步改 UI 数据读取层（API routes 不能再直接读 JSON 文件）。

## Done（留档，定期清入 CHANGELOG 后删除）

- **#6**（v0.2.5）—— zod `EvaluationResult` 补 `.superRefine`，镜像 Python `pass_fail_requires_evidence`（pass/fail 必须有 evidence_refs）；vitest 否定+肯定测试。
- **#12**（v0.2.5）—— 二进制检测统一为共享 `looks_binary`（全 buffer 扫描 `\x00`），adapter 与 artifact_store 共用；修复 null byte 在 1024 后被误判文本+误标 redacted 的 bug。
- **#1**（v0.2.4）—— 跨语言决策算法等价契约：`recomputeDecision` 补 trace cost 聚合（修复人工标注抹掉 cost 的真 bug）；新增 `decision-equivalence.json` golden（Python `build_decision` 为权威），pytest 自洽 + vitest 容差等价双端钉死算法漂移。
- **#13**（v0.2.3）—— `file_exists`/`command` expectations 验证作用域从 artifact 目录改为 agent 实际 workspace；`{output_dir}` 占位符显式引用产物目录（`validator.py` + `kernel.py`）。
- **#14**（v0.2.3）—— kernel per-cell 异常隔离：未预期异常降级为隔离失败结果（stderr 脱敏），`CancelledError` 仍向上传播；不再因单 cell 异常中止整个 run。
- **#10**（v0.2.3）—— `git_repo`/`files` workspace source path 约束在 project root 内；共享 `_assert_within_root` guard 覆盖三处入口（`_resolve_source_path`/`_copy_files`/`build_same_start_snapshot`），越界在准备期拒绝、在 same-start 快照期降级为带 task id 的 caveat。
- **Secret redaction**（2026-05-31 评审项）——`Redactor` + `MICRO_EVAL_SECRET_*` 通道覆盖 artifact/evidence/judge prompt/trace summary/validator 输出，含否定测试（v0.1.x–v0.2.1）。
- **output_mode: directory 评分机制**（2026-05-31 评审项）——adapter 支持 directory 输出收集，评分经 task-specific expectations 实现（v0.1.x–v0.2.x）。
