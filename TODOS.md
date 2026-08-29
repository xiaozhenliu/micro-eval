# Work Register

> `TODOS.md` is the only index of unfinished work on `dev`.
> Active committed work keeps one `LOCAL-...` or `GH-...` authority pointer;
> details live only in that ticket or GitHub Issue. Lanes describe planning,
> while ticket `Status`, `Triage`, and `Executor` describe execution.
> See `docs/agents/issue-tracker.md` for the contract.

## Now

（无）

## Next

- [GH-15](https://github.com/xiaozhenliu/micro-eval/issues/15) — Next.js 16.3.x 升级。

## Waiting

（无）

## Roadmap

- Task scope and diff expectations — add allowed-file and patch assertions when a real task needs to constrain or inspect agent changes. **Trigger:** a user task requires file-scope enforcement or diff-based validation.
- Deeper judge, coverage, and external-provider paths — expand LLM-judge, CLI, remote-provider, Git-worktree, and Langfuse coverage where the current optional or external boundary leaves a meaningful gap. **Trigger:** a production path, CI requirement, or reproducible defect makes one of these gaps material.
- Cost attribution ladder — support agent-reported cost, token-price estimation, and stronger Langfuse extraction only when best-effort process or trace cost is insufficient. **Trigger:** a user needs a cost comparison that current sources cannot explain.
- Run-wide controls — add run-level timeout, cancellation, and checkpoint recovery as a cohesive lifecycle feature. **Trigger:** a real long-running evaluation must resume without rerunning completed cells.
- SQLite read-model migration — move remaining UI/run and artifact lookups behind a derived data-access layer if JSON scans become a bottleneck. **Trigger:** measured run-list or artifact lookup latency requires an indexed read model.
- OpenHands provider — register and validate an OpenHands execution provider after the sandbox boundary is proven with a real task. **Trigger:** a supported OpenHands scenario exists and its workspace contract is defined.
- Windows support — add platform-specific command and sandbox behavior when compatibility is requested by users or CI. **Trigger:** a Windows user or CI target becomes part of the support promise.

## Inbox

（无）
