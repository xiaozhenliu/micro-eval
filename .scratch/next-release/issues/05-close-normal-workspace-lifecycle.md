# LOCAL-NEXT-05 — 闭合正常 workspace 生命周期

**What to build:** 让 `blank`、`files`、`git_repo` 三类本地 workspace 在正常控制流中遵守同一条最终化顺序：agent 返回后，系统在 workspace 仍存在时完成终态观察、Artifact/Evidence、deterministic validation 与可选 judgment；随后 cleanup，并通过 Store Interface 提交可复核的结果。

ID: LOCAL-NEXT-05
Type: task
Status: resolved
Triage: ready-for-agent
Executor: agent
Blocked by: None

- [x] single 与 conversational 路径共用一条 cell finalization：`prepare → snapshot gate → invoke → observe → persist facts → validate → optional judge → cleanup → commit`；不得继续维护两套 Artifact/Evidence/Evaluation/CellResult 尾段。
- [x] `blank` 和 `files` workspace 中，agent 创建或修改的文件能被 `file_exists` / command expectation 在 live workspace 中正确观察；提交后 workspace 已删除且 `cleanup_status=cleaned`。
- [x] `git_repo` 在 validator 之前持久化有界且脱敏的终态 diff：包含相对 source `HEAD` 的 staged、unstaged 与安全 untracked 文本变化；setup 造成的非 ignored 变化必须给出 caveat，validator 自身副作用不得进入该 diff。
- [x] Environment 只返回原始 workspace observation，不创建 `ArtifactRef`；ArtifactStore 负责脱敏、容量限制、持久化和 manifest 引用；symlink、hardlink、binary 与超限内容不被当作普通文本持久化。
- [x] RunStore 统一提交该 cell 的 Evaluation、CellResult 与 RunRecord projection；Execution Kernel 不再直接读写或扫描 `evaluation.json`，`on_cell_complete` 只在提交后触发。
- [x] 成功 setup 的退出码进入 CellSnapshot；没有 setup 时保持 `None`。
- [x] Integration/E2E 覆盖真实 `Kernel + Adapter + Workspace + Store` 正常闭环，包括 `blank + file_exists`、`files + command`、git tracked/untracked diff，以及 single/conversational 共同最终化；相关回归与安全检查通过。
- [x] 与 WorkspaceProvider、Artifact/Trace、Store ownership 和当前自动持久化范围有关的架构文档同步更新，文档不声称默认归档整个 `blank/files` workspace，也不把终态 diff 误写为纯 agent delta。

## Completion evidence

- Commit: `c516184 fix: close normal workspace lifecycle`
- Verification: `uv run pytest -q` — 627 passed; `compileall` and `git diff --check` passed.
- External review: Codex MCP `PASS` — model `gpt-5.5`, reasoning `xhigh`.

## Context

当前普通单轮路径在 `ExecutionKernel._execute_cell()` 的 `finally` 中先 cleanup，再把 `prepared.path` 交给 validator，因此 agent 成功创建的文件会被稳定误判为 missing。WorkspaceProvider 的 diff 能力也没有进入 Kernel 的 Artifact/Evidence 路径；single 与 conversational 又使用不同的 finalization 顺序。

实现应在现有八个顶层 Module 内完成：Execution Kernel 内部需要一个统一正常 cell lifecycle；Environment 负责 prepare/snapshot/observe/cleanup；Artifact/Trace 负责持久引用；Evaluation 读取 live workspace；Decision 只读取已持久化 Evaluation/Evidence。不新增第九个顶层 Module。

本 issue 的正常控制流包括 agent 正常返回非零退出码和 validator pass/fail；不包括取消、timeout、crash、prepare/persist/cleanup 半失败、恢复、重试或 remote session 失联。任意 workspace 文件的声明式归档、setup 后完整 prepared-state baseline、异常 lifecycle，以及 wheel 中 UI/serve 的分发契约分别另立 issue。
