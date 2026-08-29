# 未完成工作总目录

> `TODOS.md` 是 `dev` 上唯一的未完成工作总目录，只给维护者使用，不进入公开发布。
> 已承诺的工作在这里保留一个 `LOCAL-...` 或 `GH-...` 权威指针；详情只写在
> 对应的 ticket 或 GitHub Issue 中。规划 lane 表示规划位置，ticket 的
> `Status`、`Triage`、`Executor` 表示执行状态。
> `Waiting（等待解除）` 表示已经承诺但确实被阻塞的工作；`Roadmap（路线图）`
> 表示尚未承诺、尚未阻塞的未来选项。每个路线图项目都记录剩余范围和触发/晋升时机。
> 治理约定详见 `docs/agents/issue-tracker.md`。

## 当前执行（Now）

（无）

## 下一步（Next）

- [GH-15](https://github.com/xiaozhenliu/micro-eval/issues/15) — Next.js 16.3.x 升级。

## 等待解除（Waiting）

（无：当前没有已承诺但被外部条件阻塞的工作。出现此类工作时，先建立
ticket，将 `Status: blocked`、`Blocked by:` 和解除条件写入 ticket，再放入
此 lane；阻塞解除后移回 `Now` 或 `Next`。）

## 路线图（Roadmap）

- Python↔TypeScript schema 自动生成 — **规划状态：** 路线图（未阻塞）。**范围：** 评估 Pydantic `TypeAdapter.json_schema()`/JSON Schema 转 Zod 的生成方案，与当前手写 Zod schema 和 golden fixture 对照。**触发/晋升时机：** schema 同步成为反复发生的交付成本，或出现 contract drift。
- CLI 与确定性验证覆盖 — **规划状态：** 路线图（未阻塞）。**范围：** 为 CLI 入口、配置解析、run abort 和 validation error 分支补 subprocess 级覆盖（`cli/main.py`、`cli/run.py`、`cli/validate.py`）。**触发/晋升时机：** CLI 支持承诺或可复现 defect 需要这些路径被覆盖。
- 可选 judge 与 provider 覆盖 — **规划状态：** 路线图（未阻塞）。**范围：** 深入 DeepEval client fallback、E2B/Modal remote path、Git-worktree 异常清理和其他可选集成边界，同时不让普通 CI 依赖外部凭证。**触发/晋升时机：** 某个已启用的生产路径、CI 目标或可复现 defect 使某项缺口变得实际重要。
- 任务范围与 diff expectation — **规划状态：** 路线图（未阻塞）。**范围：** 在真实任务需要限制或检查 agent 修改时，增加 `allowed_files` 和 patch assertion（`models/task.py`、validator、workspace diff evidence）。**触发/晋升时机：** 用户任务需要文件范围约束或 diff 验证。
- agent 自报 cost — **规划状态：** 路线图（未阻塞）。**范围：** 增加 agent 自报 cost 字段和明确的上报格式，并规定它与 Langfuse cost 的优先级。**触发/晋升时机：** 被评估 agent 能提供 process telemetry 无法提供的可信 cost 数据。
- token × price cost 估算 — **规划状态：** 路线图（未阻塞）。**范围：** 增加维护中的模型价格表和基于 token 的 estimated cost source。**触发/晋升时机：** 当前 process、自报和 Langfuse source 都无法解释用户所需的精确 cost 对比。
- Langfuse cost 提取 — **规划状态：** 路线图（未阻塞）。**范围：** 固定或 contract-test 可选 SDK 的 payload 结构，并改进 best-effort 提取。**触发/晋升时机：** SDK 稳定性改善，或用户报告 cost 提取存在实质不准确。
- run 级控制 — **规划状态：** 路线图（未阻塞）。**范围：** 作为一项完整生命周期功能增加 run-level timeout、取消和 checkpoint recovery。**触发/晋升时机：** 真实的长时间 evaluation 必须在不重跑已完成 cell 的情况下恢复。
- SQLite 读模型迁移 — **规划状态：** 路线图（未阻塞）。**范围：** 将剩余 run/cell/artifact JSON 读取迁移到 derived SQLite data-access layer，并为 artifact lookup 建索引。**触发/晋升时机：** 测量到 run list 或 artifact lookup 延迟需要 indexed read model。
- OpenHands provider — **规划状态：** 路线图（未阻塞）。**范围：** 在 sandbox 和 workspace 映射验证完成后注册并验证 OpenHands execution provider。**触发/晋升时机：** 出现受支持的 OpenHands 场景，并定义好它的 workspace contract。
- Windows 兼容性 — **规划状态：** 路线图（未阻塞）。**范围：** 增加平台专用命令解析和 sandbox 行为，并明确支持边界。**触发/晋升时机：** Windows 用户或 CI 目标成为支持承诺的一部分。

## 收件箱（Inbox）

（无）
