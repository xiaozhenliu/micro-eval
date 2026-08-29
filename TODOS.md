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

- Python↔TypeScript schema generation — evaluate Pydantic `TypeAdapter.json_schema()`/JSON Schema to Zod generation against the current hand-maintained Zod schemas and golden fixtures. **Trigger:** schema synchronization becomes a recurring delivery cost or causes a contract drift.
- CLI and deterministic validation coverage — add subprocess-level coverage for CLI entry, config parsing, run abort, and validation error branches (`cli/main.py`, `cli/run.py`, `cli/validate.py`). **Trigger:** the CLI support promise or a reproducible defect requires these paths to be covered.
- Optional judge and provider coverage — deepen DeepEval client fallback, E2B/Modal remote paths, Git-worktree exceptional cleanup, and other optional integration boundaries without requiring external credentials in ordinary CI. **Trigger:** an enabled production path, CI target, or reproducible defect makes one gap material.
- Task scope and diff expectations — add `allowed_files` and patch assertions when a real task needs to constrain or inspect agent changes (`models/task.py`, validator, and workspace diff evidence). **Trigger:** a user task requires file-scope enforcement or diff-based validation.
- Agent-reported cost — add an agent-reported cost field and an explicit reporting format, then define its precedence against Langfuse cost. **Trigger:** an evaluated agent can provide trustworthy cost data that process-level telemetry cannot provide.
- Token × price cost estimation — add a maintained model-price table and token-based estimated cost source. **Trigger:** a user needs precise cost comparison that current process, self-reported, and Langfuse sources cannot explain.
- Langfuse cost extraction — pin or contract-test the optional SDK payload shape and improve best-effort extraction. **Trigger:** SDK stability improves or a user reports materially inaccurate cost extraction.
- Run-wide controls — add run-level timeout, cancellation, and checkpoint recovery as a cohesive lifecycle feature. **Trigger:** a real long-running evaluation must resume without rerunning completed cells.
- SQLite read-model migration — move the remaining run/cell/artifact JSON reads behind the derived SQLite data-access layer and index artifact lookup. **Trigger:** measured run-list or artifact lookup latency requires an indexed read model.
- OpenHands provider — register and validate an OpenHands execution provider after sandbox and workspace mapping are proven. **Trigger:** a supported OpenHands scenario exists and its workspace contract is defined.
- Windows support — add platform-specific command resolution and sandbox behavior, with an explicit support boundary. **Trigger:** a Windows user or CI target becomes part of the support promise.

## Inbox

（无）
