# LOCAL-WORK-GOVERNANCE-02 — 归档已解决的本地 ticket

**What to build:** 将 `.scratch/` 下全部 12 个 `Status: resolved` 的本地 ticket 移入 per-effort 的 `issues/resolved/` 归档子目录，使 `issues/` 只呈现活跃 ticket。同步更新 effort map 链接、`docs/agents/issue-tracker.md` 的路径约定，以及 `scripts/check-work-governance.py` 的 `.scratch` 路径白名单与 ticket 扫描逻辑。归档 ticket 保留原有 `Status: resolved` 与完成证据，仅改变存放位置；归档文件继续参与 ID 唯一性校验，防止编号复用。

ID: LOCAL-WORK-GOVERNANCE-02
Type: governance
Status: resolved
Triage: ready-for-agent
Executor: agent
Blocked by: None

## Acceptance criteria

- 12 个 resolved ticket 以 `git mv` 移入各自 effort 的 `issues/resolved/`，文件内容与 ID 不变。
- 两个 `map.md` 的相对链接指向新位置。
- `docs/agents/issue-tracker.md` 记录 `issues/resolved/` 归档约定：活跃 ticket 在 `issues/`，resolved ticket 归档到 `issues/resolved/`，归档不改变 ticket 的权威内容。
- `scripts/check-work-governance.py` 白名单接受 `issues/resolved/NN-kebab.md`；活跃 ticket 扫描（`*/issues/*.md`）不受归档影响；归档 ticket 的 ID 纳入重复检测。
- `python3 scripts/check-work-governance.py` 通过。
- 公开发布投影策略无需变化（`.scratch/**` 整体 private）。

## Context

- 当前 `.scratch/next-release/issues/` 有 11 个、`.scratch/work-governance/issues/` 有 1 个 resolved ticket，全部完成且已从 `TODOS.md` 移除；随着工作累积，活跃与已解决 ticket 混放会降低可读性。
- 治理检查脚本对 `.scratch` 下文件路径有白名单（`check-work-governance.py:309-321`），新增子目录必须显式放宽，否则检查失败。
- ticket 是完成证据的权威来源之一，归档必须保留文件全文与 git 历史，不得删除或改写证据。

## Completion evidence

- 12 个 resolved ticket 经 `git mv` 移入 `.scratch/next-release/issues/resolved/`（11 个）与 `.scratch/work-governance/issues/resolved/`（1 个），内容与 ID 未变。
- `.scratch/next-release/map.md` 与 `.scratch/work-governance/map.md` 链接已指向 `issues/resolved/`。
- `docs/agents/issue-tracker.md` 增加归档约定：活跃 ticket 在 `issues/`，全部解决后归档到 `issues/resolved/`，归档保留 ID、状态与证据，归档 ID 继续参与唯一性校验。
- `scripts/check-work-governance.py`：`.scratch` 白名单接受 `issues/resolved/NN-kebab.md`；新增 `_check_archived_tickets`，校验归档文件名、ID 格式及与活跃/归档 ticket 的 ID 冲突。
- 验证：`python3 scripts/check-work-governance.py` 通过；`pytest tests/unit/test_work_governance.py` 5 passed（含新增归档用例 2 个）。
