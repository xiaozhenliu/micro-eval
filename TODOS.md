# Work Register

> `TODOS.md` is the only index of unfinished work on `dev`.
> Active committed work keeps one `LOCAL-...` or `GH-...` authority pointer;
> details live only in that ticket or GitHub Issue. Lanes describe planning,
> while ticket `Status`, `Triage`, and `Executor` describe execution.
> `Waiting` means committed work is actually blocked and has a ticket;
> `Roadmap` means an uncommitted future option, not a blocked ticket. Every
> Roadmap item records its remaining scope and its `Trigger / promote when`.
> See `docs/agents/issue-tracker.md` for the contract.

## Now

（无）

## Next

- [GH-15](https://github.com/xiaozhenliu/micro-eval/issues/15) — Next.js 16.3.x 升级。

## Waiting

（无：当前没有已承诺但被外部条件阻塞的工作。出现此类工作时，先建立
ticket，将 `Status: blocked`、`Blocked by:` 和解除条件写入 ticket，再放入
此 lane；阻塞解除后移回 `Now` 或 `Next`。）

## Roadmap

- Python↔TypeScript schema generation — **Planning state:** Roadmap (not blocked). **Scope:** evaluate Pydantic `TypeAdapter.json_schema()`/JSON Schema to Zod generation against the current hand-maintained Zod schemas and golden fixtures. **Trigger / promote when:** schema synchronization becomes a recurring delivery cost or causes a contract drift.
- CLI and deterministic validation coverage — **Planning state:** Roadmap (not blocked). **Scope:** add subprocess-level coverage for CLI entry, config parsing, run abort, and validation error branches (`cli/main.py`, `cli/run.py`, `cli/validate.py`). **Trigger / promote when:** the CLI support promise or a reproducible defect requires these paths to be covered.
- Optional judge and provider coverage — **Planning state:** Roadmap (not blocked). **Scope:** deepen DeepEval client fallback, E2B/Modal remote paths, Git-worktree exceptional cleanup, and other optional integration boundaries without requiring external credentials in ordinary CI. **Trigger / promote when:** an enabled production path, CI target, or reproducible defect makes one gap material.
- Task scope and diff expectations — **Planning state:** Roadmap (not blocked). **Scope:** add `allowed_files` and patch assertions when a real task needs to constrain or inspect agent changes (`models/task.py`, validator, and workspace diff evidence). **Trigger / promote when:** a user task requires file-scope enforcement or diff-based validation.
- Agent-reported cost — **Planning state:** Roadmap (not blocked). **Scope:** add an agent-reported cost field and an explicit reporting format, then define its precedence against Langfuse cost. **Trigger / promote when:** an evaluated agent can provide trustworthy cost data that process-level telemetry cannot provide.
- Token × price cost estimation — **Planning state:** Roadmap (not blocked). **Scope:** add a maintained model-price table and token-based estimated cost source. **Trigger / promote when:** a user needs precise cost comparison that current process, self-reported, and Langfuse sources cannot explain.
- Langfuse cost extraction — **Planning state:** Roadmap (not blocked). **Scope:** pin or contract-test the optional SDK payload shape and improve best-effort extraction. **Trigger / promote when:** SDK stability improves or a user reports materially inaccurate cost extraction.
- Run-wide controls — **Planning state:** Roadmap (not blocked). **Scope:** add run-level timeout, cancellation, and checkpoint recovery as a cohesive lifecycle feature. **Trigger / promote when:** a real long-running evaluation must resume without rerunning completed cells.
- SQLite read-model migration — **Planning state:** Roadmap (not blocked). **Scope:** move the remaining run/cell/artifact JSON reads behind the derived SQLite data-access layer and index artifact lookup. **Trigger / promote when:** measured run-list or artifact lookup latency requires an indexed read model.
- OpenHands provider — **Planning state:** Roadmap (not blocked). **Scope:** register and validate an OpenHands execution provider after sandbox and workspace mapping are proven. **Trigger / promote when:** a supported OpenHands scenario exists and its workspace contract is defined.
- Windows support — **Planning state:** Roadmap (not blocked). **Scope:** add platform-specific command resolution and sandbox behavior, with an explicit support boundary. **Trigger / promote when:** a Windows user or CI target becomes part of the support promise.

## Inbox

（无）
