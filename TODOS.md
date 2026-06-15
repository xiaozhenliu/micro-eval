# TODOS.md

> **格式约定**（整理时遵守）：
> - 状态只有两种分组：**Ready**（已核实、可动手，按优先级排）/ **Blocked**（必填解除条件，整理时机械检查是否可移入 Ready）。
> - 优先级标尺：**P0** 正确性 bug 与里程碑 / **P1** 安全、双端一致性 / **P2** 质量、测试、重构 / **P3** 顺手项。
> - **有 GitHub issue 的事项只留一行指针**（编号 + 一句话 + 标签），详情以 issue 为权威，避免双源漂移。
> - **无 issue 的事项必须展开**：待做事项 + 关联文件，信息密度达到"新会话不靠考古就能动手"。
> - 完成项一行留档进 Done，定期清入 CHANGELOG 后删除。
>
> 最近整理：2026-06-15（v0.3.2 发布后）。v0.3.2 测试覆盖率从 ~78%（224 tests）提升到 91%（455 tests），关闭 CLI、engine、evaluation、store、trace 各层缺口。P0/P1 已清空。

---

## Ready

### P0

*(P0 已清空)*

### P1

*(P1 已清空)*

### P2

#### CI: 新 example smoke 接入

- **关联文件:** `.github/workflows/ci.yml`（`example-smoke` job 当前只跑 `run-example.py` 默认 example）。
- **待做:** CI smoke job 改为 `python examples/run-example.py --example all`，或分拆三个并行 job 各跑一个 example。`git-workspace-isolation` 需要 `git` 可用（CI ubuntu 默认有）。
- **风险:** 无。改一行 CI 配置即可。

#### 占位符解析不一致：`{python}` 仅在 agent command 中生效

- **现状:** `AgentAdapter._resolve_command()`（`engine/adapter.py:215-225`）解析 `{python}`/`{output_file}`/`{input_file}`/`{output_dir}`。但 workspace setup commands（`providers/git_worktree.py:207-223`）和 command expectations（`evaluation/validator.py:135-162`）直接 `subprocess.run`/`create_subprocess_exec`，不走占位符解析。
- **影响:** 用户在 task YAML 的 `setup` 或 command expectation 中写 `{python}` 会当作字面字符串执行并失败。当前 example 用 `python3` 规避，但与 agent command 用 `{python}` 的体验不一致。
- **待做:** ① 在 workspace provider `_run_setup` 和 validator `_run_validation_command` 中共享占位符解析逻辑（提取 `adapter.py` 中的 replacements dict 为公共函数）；② 更新文档说明统一占位符。schema 无变化，仅执行层改动。
- **关联文件:** `engine/adapter.py`（现有解析）、`engine/providers/git_worktree.py`（setup）、`evaluation/validator.py`（command expectation）。

#### #9 错误分类 enum 重构（残留项）

- **已交付:** v0.2.9 concurrency=4 + artifact cap 50MB + truncation flag 持久化；spec 对齐。
- **仅剩:** `AdapterResult.status` 用字符串 `"pass"/"fail"/"error"/"timeout"` 区分，应改为 enum 并区分 crash vs timeout vs user error。低价值，有回归风险。
- **关联文件:** `engine/adapter.py`（`AdapterResult`）、`engine/kernel.py`（消费 status）、`models/run.py`（`CellResult`）。

#### 测试覆盖率（已大幅提升，v0.3.2）

- **整体覆盖率:** 91%（455 tests）。前版本 ~78%（224 tests）。
- **当前剩余缺口（<100% 文件）:**

| 文件 | 覆盖率 | 缺口说明 |
|------|--------|----------|
| `cli/main.py` | 58% | Typer app 入口分支（`main()` 调用路径），需 subprocess 级 e2e |
| `cli/run.py` | 79% | 部分 error-path 分支（--config 解析失败、run abort） |
| `cli/validate.py` | 82% | 部分错误分支 |
| `evaluation/llm_judge.py` | 65% | DeepEval client 封装路径（Blocked，见下） |
| `engine/providers/remote.py` | 44% | E2B/Modal 远程执行路径（需真实凭证或重 mock） |
| `engine/providers/git_worktree.py` | 85% | worktree 创建/清理异常路径 |
| `trace/langfuse_provider.py` | 80% | SDK 降级路径（Blocked，见下） |

- **待做（低优先级，已超 CI 门槛 75%）:** `cli/main.py` 补 subprocess 级 e2e；`remote.py` 补完整 mock 路径。其余缺口受外部依赖限制（Blocked）。

### P3

#### Python↔TypeScript schema 同步自动化

- **现状:** Pydantic model → 手写 zod schema → golden fixture 三方守护。每次加/改字段需同步三处。
- **待做:** 调研 codegen 方案（pydantic → zod / JSON Schema → zod），评估是否值得引入。可能的路径：`pydantic.TypeAdapter.json_schema()` → `json-schema-to-zod`。
- **风险:** codegen 可能产出不符合项目 style 的 zod 代码，需评估可维护性。
- **关联文件:** `src/micro_eval/models/`（Pydantic）、`ui/src/lib/schemas/`（zod）、`scripts/generate-golden.py`。

#### UI 无 `localStorage`/`sessionStorage` 使用（已清零，保持监控）

- **现状:** 全部 UI 评估状态经 API 持久化到 `evaluation.json`。`localStorage`/`sessionStorage` grep 为零。
- **待做:** 无。CI 的 `grep -R "localStorage" ui/src` 安全 grep 已覆盖。仅作为监控项保留。

---

## Blocked

### LLM Judge DeepEval client 封装测试

- **解除条件:** LLM judge 进入真实生产链路（有用户实际启用 judge 评分）。
- **关联文件:** `src/micro_eval/evaluation/llm_judge.py`（当前覆盖 65%）。
- **待做:** 补 DeepEval client 封装与 score 解析分支的测试——缺口集中在外部依赖路径（client 初始化失败、API 返回异常 score、解析降级）。需 mock DeepEval client。

### Task 模型增强：allowed-files 白名单 + diff expectations

- **解除条件:** 出现需要限制 agent 改动范围或对 diff 做断言的真实任务用例。
- **关联文件:** `src/micro_eval/models/task.py`（ExpectationSpec）、`src/micro_eval/evaluation/validator.py`、`src/micro_eval/engine/workspace.py`（`collect_diff` 已产出 patch artifact，可作为断言输入）。
- **待做:** ① Task 模型加 `allowed_files` 字段 + validator 校验 diff 是否越界；② 新增 diff 类 expectation（对 patch 内容断言）。schema 改动需同步 ui 端 zod 与 contract golden。
- **已交付部分:** WorkspaceSpec（git_repo/files/setup）、ExpectationSpec（exit_code/contains/file_exists/command）、`collect_diff` patch artifact。

### Agent 自报 cost 字段（#7 关闭时剩余项）

- **解除条件:** 出现会上报 cost 的真实 agent（cost ladder 第 2 级）。
- **关联文件:** `src/micro_eval/engine/adapter.py`（AdapterResult）、`src/micro_eval/models/run.py`（CellResult）、contract golden（`scripts/generate-golden.py`）。
- **待做:** AdapterResult/CellResult 增加 agent 自报 cost 字段，约定上报格式（stdout 标记或文件），与 Langfuse cost 的优先级关系写入 spec。

### Token × price cost 估算（cost ladder 第 3 级）

- **解除条件:** 有用户需要精确 cost 对比（不满足 Langfuse best-effort 或 agent 自报）。
- **关联文件:** `src/micro_eval/models/decision.py`（`CostMetric`）、`src/micro_eval/decision/aggregation.py`。
- **待做:** 实现 token count × model price table 的 cost 估算。需维护主流模型的 price table 或接入外部 pricing API。
- **已有基础:** `CostMetric.source` 已区分 `unavailable`/`process`/`langfuse`，可加 `estimated` 源。

### Langfuse cost 提取改进

- **解除条件:** Langfuse SDK 稳定化或有用户报告 cost 提取不准。
- **现状:** best-effort，依赖 SDK runtime payload 形状。SDK 升级可能 break。
- **关联文件:** `src/micro_eval/trace/langfuse_provider.py`（覆盖 80%）。
- **待做:** pin Langfuse SDK 版本 + 加集成测试 mock 验证 payload 形状。

### Run 级全局超时 / 取消 / 断点恢复

- **解除条件:** 实际使用中出现长 run 被迫整体重跑的反馈。
- **关联文件:** `src/micro_eval/engine/kernel.py`、`src/micro_eval/cli/run.py`。
- **待做:** ① run 级 wall-clock 超时；② SIGINT 优雅取消（已完成 cell 落盘）；③ 断点恢复（跳过已有结果的 cell 重跑剩余矩阵）。三项可独立交付，断点恢复依赖 run_store 的 cell 级幂等写入。
- **已交付部分:** `--max-concurrency`（CLI + guardrails）、per-cell timeout、`stop_on_cell_error`。

### JSON → SQLite 全面迁移（已部分交付 — P3-e）

- **已交付（v0.3.0）:** SQLite 索引层 `sqlite_store.py`（JSON 仍为 source of truth），趋势 API route 经 SQLite 查询（`ui/src/app/api/trends/route.ts` 用 `better-sqlite3`）。
- **剩余:**
  - UI 的 6 个 API route（runs、run detail、cell、artifact、evaluate、trace）仍直读 JSON 文件（`fs.readFileSync` + `JSON.parse`）。需改经统一 data access layer 或 SQLite。
  - `artifact_store` 无 SQLite 索引（artifact 查找经 manifest.json 线性扫描）。
- **解除条件:** UI 性能出现瓶颈（大量 run 列表加载慢），或 artifact 数量增长导致 manifest 扫描变慢。
- **关联文件:** `ui/src/app/api/runs/` 下全部 route.ts（6 个文件）、`src/micro_eval/store/sqlite_store.py`、`src/micro_eval/store/artifact_store.py`。

### OpenHands 接入（Phase 3 路线图项）

- **解除条件:** Phase 3 sandbox 基础设施验证完毕（已完成）+ 有真实的 OpenHands 任务场景。
- **待做:** 在 provider registry 中注册 OpenHands provider，将 agent command 委托给 OpenHands 运行时。需评估 OpenHands API 稳定性和 workspace 映射。
- **关联文件:** `src/micro_eval/engine/providers/`（注册新 provider）、`src/micro_eval/models/task.py`（可能需要新 IsolationLevel）。

### Windows 兼容性

- **解除条件:** 有 Windows 用户或 CI 需求。
- **现状:** command expectations 和 setup commands 硬编码 `python3`（Windows 上需 `python` 或 `py`）。`{python}` 占位符解析仅在 agent command 中生效（见 Ready P2 占位符统一项）。Seatbelt/Bubblewrap 仅 macOS/Linux。
- **待做:** 占位符统一后自动解决 Python 路径问题。Sandbox provider 需增加 Windows 降级逻辑（或文档标注不支持）。
- **关联文件:** `evaluation/validator.py`、`engine/providers/git_worktree.py`、example task YAML。

---

## Done（留档，定期清入 CHANGELOG 后删除）

- **Test coverage expansion**（v0.3.2）—— 整体覆盖率从 ~78%（224 tests）提升到 91%（455 tests）。CLI 层（init/list/run/validate/report）从 0% 提升至 82%+；decision/trend 达到 100%；engine/workspace 达到 99%；models/configuration、models/run 达到 100%。455 pytest 全绿。
- **Example coverage expansion**（v0.3.1）—— 新增 `multi-task-matrix`（12-cell 矩阵，4 种 expectation，setup commands）+ `git-workspace-isolation`（git_repo worktree、OS sandbox、fixture digest、toolchain fingerprint、趋势分析 drift breakpoint）。`run-example.py` 加 `--example` 统一入口。examples/README.md 加能力覆盖矩阵 + Advanced 外部集成文档。覆盖度 ~50% → ~85%。独立 opus 评审 → 修复 6 项反馈后 commit。224 pytest + 48 vitest 全绿。
- **Phase 3 实施**（v0.3.0）—— P3-a→P3-e 五个里程碑全部交付。详见 CHANGELOG 0.3.0。
- **v0.2.2–v0.2.10** —— 所有 GitHub issue #1–#14 解决。详见 CHANGELOG 各版本条目。
