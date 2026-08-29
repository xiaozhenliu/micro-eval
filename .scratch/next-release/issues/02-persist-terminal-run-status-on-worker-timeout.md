# LOCAL-NEXT-02 — 保证 Team Server 超时后的运行状态一致

**What to build:** 当 Team Server worker 因运行超时终止任务时，让队列中的 job 与持久化运行记录都进入一致、可解释的终态，避免用户看到 job 已失败但 run 仍显示运行中的矛盾状态。

ID: LOCAL-NEXT-02
Type: task
Status: resolved
Triage: ready-for-agent
Executor: agent
Blocked by: None

- [x] worker 超时后，queue job 与持久化运行记录均不再停留在 `running`，并记录可理解且经过脱敏的超时原因。
- [x] 状态更新在进程重启后仍可恢复，不产生无法被恢复逻辑识别的半完成记录。
- [x] 正常完成、执行异常、取消和已有恢复路径的行为不回归。
- [x] 超时状态一致性具有自动化回归验证，相关安全检查通过。

## Completion evidence

- Commit: `f21cf35`.
- Verification: worker-loop timeout, terminal failure persistence, recovery, and redaction coverage passed.
- Release trace: `CHANGELOG.md` v0.4.5.
