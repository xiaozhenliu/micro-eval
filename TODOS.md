# 未完成工作总目录

> `TODOS.md` 是 `dev` 上唯一的未完成工作总目录，只给维护者使用，不进入公开发布。
>
> - 已承诺的工作在这里保留一个 `LOCAL-...` 或 `GH-...` 权威指针；详情只写在
>   对应的 ticket 或 GitHub Issue 中。
> - 规划 lane 表示规划位置，ticket frontmatter 的 `status`、`triage`、`executor`
>   表示执行状态。
> - `Waiting（等待解除）` 表示已经承诺但确实被阻塞的工作。
> - `Roadmap（路线图）` 表示尚未承诺、尚未阻塞的未来选项；每项记录剩余范围和
>   触发/晋升时机。
>
> 治理约定详见 `docs/agents/issue-tracker.md`。

## 当前执行（Now）

（无）

## 下一步（Next）

- [LOCAL-COMPARATIVE-DECISION-01](.scratch/comparative-decision/issues/01-emit-comparative-verdict.md) — 为单 baseline/candidate run 产出证据受保护的比较结论。
- [GH-15](https://github.com/xiaozhenliu/micro-eval/issues/15) — Next.js 16.3.x 升级。

## 等待解除（Waiting）

（无）

> 当前没有已承诺但被外部条件阻塞的工作。出现此类工作时，先建立 ticket，
> 将 `status: blocked`、`blocked_by` 和解除条件写入 ticket frontmatter，再放入此 lane；
> 阻塞解除后移回 `Now` 或 `Next`。

## 路线图（Roadmap）

以下各项规划状态均为「路线图（未阻塞）」；触发条件满足时晋升为 ticket 并进入
`Now` 或 `Next`。`#` 列仅为讨论引用用的行序号，不代表 ticket 编号。
`优先级` 是当前评估的相对重要性（高/中/低），只作为晋升时的参考排序，
不取代触发条件；评估依据写在括号内。表格按优先级降序排列。

| # | 优先级 | 项目 | 剩余范围 | 触发 / 晋升时机 |
| --- | --- | --- | --- | --- |
| 1 | 高（CLI 是主要用户入口，abort / validation 分支缺 subprocess 级回归保护） | CLI 与确定性验证覆盖 | 为 CLI 入口、配置解析、run abort 和 validation error 分支补 subprocess 级覆盖（`cli/main.py`、`cli/run.py`、`cli/validate.py`）。 | CLI 支持承诺或可复现 defect 需要这些路径被覆盖。 |
| 2 | 中（直接增强评估表达能力，agent 基准场景的常见需求） | 任务范围与 diff expectation | 在真实任务需要限制或检查 agent 修改时，增加 `allowed_files` 和 patch assertion（`models/task.py`、validator、workspace diff evidence）。 | 用户任务需要文件范围约束或 diff 验证。 |
| 3 | 中（跨语言 contract 靠手写 Zod + golden 维持，drift 成本随 UI 演进上升） | Python↔TypeScript schema 自动生成 | 评估 Pydantic `TypeAdapter.json_schema()` / JSON Schema 转 Zod 的生成方案，与当前手写 Zod schema 和 golden fixture 对照。 | schema 同步成为反复发生的交付成本，或出现 contract drift。 |
| 4 | 中（长 evaluation 恢复是真实场景，但实现面大，可等实际需求触发） | run 级控制 | 作为一项完整生命周期功能增加 run-level timeout、取消和 checkpoint recovery。 | 真实的长时间 evaluation 必须在不重跑已完成 cell 的情况下恢复。 |
| 5 | 低（best-effort 提取已可用；三项 cost 工作中最可操作的一项） | Langfuse cost 提取 | 固定或 contract-test 可选 SDK 的 payload 结构，并改进 best-effort 提取。 | SDK 稳定性改善，或用户报告 cost 提取存在实质不准确。 |
| 6 | 低（依赖被评估 agent 配合，现阶段 process telemetry 可覆盖） | agent 自报 cost | 增加 agent 自报 cost 字段和明确的上报格式，并规定它与 Langfuse cost 的优先级。 | 被评估 agent 能提供 process telemetry 无法提供的可信 cost 数据。 |
| 7 | 低（需维护价格表，仅当现有 source 都不足以解释 cost 对比时值得） | token × price cost 估算 | 增加维护中的模型价格表和基于 token 的 estimated cost source。 | 当前 process、自报和 Langfuse source 都无法解释用户所需的精确 cost 对比。 |
| 8 | 低（可选集成边界，普通 CI 不依赖外部凭证的现状可接受） | 可选 judge 与 provider 覆盖 | 深入 DeepEval client fallback、E2B/Modal remote path、Git-worktree 异常清理和其他可选集成边界，同时不让普通 CI 依赖外部凭证。 | 某个已启用的生产路径、CI 目标或可复现 defect 使某项缺口变得实际重要。 |
| 9 | 低（纯性能驱动，需先测量到实际延迟） | SQLite 读模型迁移 | 将剩余 run/cell/artifact JSON 读取迁移到 derived SQLite data-access layer，并为 artifact lookup 建索引。 | 测量到 run list 或 artifact lookup 延迟需要 indexed read model。 |
| 10 | 低（需先出现受支持的 OpenHands 场景） | OpenHands provider | 在 sandbox 和 workspace 映射验证完成后注册并验证 OpenHands execution provider。 | 出现受支持的 OpenHands 场景，并定义好它的 workspace contract。 |
| 11 | 低（需 Windows 用户或 CI 目标成为支持承诺） | Windows 兼容性 | 增加平台专用命令解析和 sandbox 行为，并明确支持边界。 | Windows 用户或 CI 目标成为支持承诺的一部分。 |

## 收件箱（Inbox）

（无）
