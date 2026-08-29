# LOCAL-WORK-GOVERNANCE-01 — 重建项目工作追踪治理

**What to build:** 建立一套只有一个工作总入口、详情只有一个权威来源、完成记录有明确归宿的项目治理机制。`TODOS.md` 应覆盖所有未完成工作；进入本地 ticket 或 GitHub Issue 的事项只在 `TODOS.md` 保留可导航的指针；尚未进入执行阶段的远期规划继续以内联 Roadmap 项存在。

ID: LOCAL-WORK-GOVERNANCE-01
Type: governance
Status: resolved
Triage: ready-for-agent
Executor: agent
Blocked by: None

## Confirmed decisions

- 日常开发与治理变更只发生在 `dev`；`main` 仍是经过验证的公开发布投影。
- `TODOS.md` 是所有未完成工作的总目录，拥有工作是否存在、portfolio lane 与规划顺序；ticket lifecycle 不在其中定义。
- 本地 ticket、GitHub Issue 各自拥有所指工作的范围、验收条件、依赖、执行状态、讨论与完成证据；不得复制两份详情。
- `.scratch/` 是 `dev` 上受 git 管理的私有工作记录区，用于本地 ticket、spec 与 map，不再视为未跟踪缓存目录。
- GitHub Issue 用于公开反馈或确实需要公开协作的工作；内部治理和实施工作默认使用本地 ticket。
- `.scratch/**` 不得进入 `main`、公开远端、wheel 或 sdist；发布投影继续将其归类为 private，并在公开树中禁止出现。
- 已完成工作从 `TODOS.md` 移除，交付事实进入 `CHANGELOG.md`，开发过程与验证证据进入 dev log 或对应 ticket。

## Context

当前治理存在多处漂移：

- `TODOS.md` 仍以 v0.3.2 为整理基线，包含已经完成或已经失真的事项，同时遗漏当前开放的 GitHub Issue #15。
- 已解决的 `{python}` 占位符工作仍列在 Ready；`AdapterResult.status` 已使用 enum，但 TODO 仍要求 enum 重构；UI 已使用 `localStorage`，TODO 却声称使用量为零。
- Ready、Blocked、Roadmap、triage role 和 ticket lifecycle status 混为一套状态语言。
- `docs/agents/issue-tracker.md` 声称 `.scratch/` 是 tracker，但 `.scratch/` 此前被 git 忽略；同时该公开文档指向不会出现在 `main` 的私有路径。
- `CLAUDE.md` 仍保留过时的手工 merge 到 `main` 说明和易失真的版本状态摘要，与当前 `AGENTS.md` 的发布模型冲突。
- GitHub Issue 标题中的 `[P8]` 与 `TODOS.md` 的 P0–P3 优先级命名发生语义冲突。

## Scope

### 1. Define the work model

- 明确定义 Work Register、Roadmap item、本地 ticket、GitHub Issue、完成证据五类对象及其唯一职责。
- 将规划阶段与执行状态拆开：`TODOS.md` 记录 portfolio lane，本地 ticket/Issue 记录 lifecycle status。
- 定义稳定且无歧义的来源标识，例如 `LOCAL-<effort>-<NN>` 与 `GH-<number>`；不再用裸 `#15` 或 `[P8]` 同时表示编号、波次或优先级。
- 定义必须先有 ticket 的工作阈值，以及从 Inbox/Roadmap 晋升为 ticket/Issue、阻塞、完成和归档的流程。

### 2. Rebuild `TODOS.md`

- 将文件定位改为“所有未完成工作的总目录”，而不是详情库或完成历史库。
- 使用清晰的 portfolio lanes，例如 Now、Next、Waiting、Roadmap 与 Inbox；只有 Roadmap/Inbox 允许保留简短内联描述。
- Now、Next 与已经承诺的 Waiting 项必须链接到一个且仅一个本地 ticket 或 GitHub Issue。
- 加入 `GH-15` Next.js 16.3.x 升级指针。
- 删除已完成、已失真或纯监控性质的条目；将真正的远期选项从 Blocked 移入 Roadmap，并为其保留触发条件。
- 删除长期 Done 档案；完成信息迁移到 `CHANGELOG.md` 或 dev log。

### 3. Make local tickets durable on `dev`

- 从 `dev` 的根 `.gitignore` 中移除 `.scratch/`，将现有和后续本地 ticket 纳入版本控制。
- 为 `.scratch/` 定义允许内容：ticket、spec、map 及其必要附件；缓存、构建产物、运行数据和秘密信息不得进入该目录。
- 统一本地 ticket 的必要字段、状态枚举、文件命名、阻塞关系和完成证据格式。
- 审计现有 `next-release` ticket：规范终态名称，并确保其交付事实可由 commit、dev log、CHANGELOG 或 release evidence 追溯。

### 4. Align governance documents and agent entry points

- 重写 `docs/agents/issue-tracker.md`，说明 `TODOS.md`、本地 ticket 和 GitHub Issue 的职责及选择规则。
- 修正或合并 `docs/agents/triage-labels.md`，将 triage role、executor 和 lifecycle status 分离。
- 更新 `docs/README.md`、`docs/dev/README.md` 与 `docs/documentation-standard.md`，登记工作治理位置和 ticket 文档规范。
- 更新 `CLAUDE.md`，删除过时的手工 merge 和静态“当前状态”，改为链接 `AGENTS.md`、`VERSION`、`CHANGELOG.md`、`TODOS.md` 与治理规范。
- 在 `AGENTS.md` 及其发布模板中加入 branch-aware 的 ticket-first 规则：`dev` 上的非微小实现必须先在 `TODOS.md` 中登记并链接权威 ticket/Issue；`main` 上仍不得开展源代码开发。
- 解决公开 `docs/agents/**` 与私有 `.scratch/**` 的可见性矛盾：公开文档不得包含在公开投影中必然失效的内部链接。

### 5. Add lightweight governance verification

- 检查 `TODOS.md` 中的本地链接确实存在。
- 检查 Now/Next 项都有唯一 ticket/Issue 指针，Roadmap 项都有明确触发条件。
- 检查 active 区域不指向已经处于终态的本地 ticket。
- 检查 `.scratch/**` 始终被公开投影归类为 private，并继续命中 forbidden-public gate。
- GitHub 状态不作为普通 CI 的联网依赖；在人工 triage 时核验 open/closed 状态。

## Acceptance criteria

- [x] `TODOS.md` 能完整列出所有未完成工作，并且没有已经完成或客观失真的条目。
- [x] 每个已进入执行阶段的工作在 `TODOS.md` 中只有一个权威 ticket/Issue 指针，详情不重复。
- [x] 远期规划与真实阻塞工作分离，Roadmap 项均包含进入执行阶段的触发条件。
- [x] `.scratch/` 中的本地工作记录由 `dev` 的 git 正常跟踪，换一台机器或重新 clone `dev` 后仍可获得。
- [x] `.scratch/**` 在候选公开树、`main`、wheel 和 sdist 中均不可出现。
- [x] 本地 ticket 状态与 triage role 使用不同字段，现有 `resolved`/`completed` 分歧被统一。
- [x] `CLAUDE.md`、`AGENTS.md`、tracker 规范、文档目录说明与发布投影不存在互相矛盾的治理陈述。
- [x] GitHub Issue #15 只作为 `GH-15` 指针出现在 Work Register 中，其正文仍是该工作的唯一公开详情来源。
- [x] 治理检查、发布投影 plan、相关 release integration tests 和 `git diff --check` 全部通过。

## Non-goals

- 不在本 ticket 中升级 Next.js 或实施工作台功能。
- 不关闭、重写或迁移 GitHub Issue #15；任何 GitHub 写操作仍需单独授权。
- 不改变 `dev` 到 `main` 的验证发布机制。
- 不把 `.scratch/`、`TODOS.md` 或其他私有开发状态发布到公开远端。

## Verification

- `git check-ignore .scratch/work-governance/issues/01-rebuild-work-tracking-governance.md` 应无匹配。
- `git ls-files .scratch/` 应列出本 ticket 与既有本地 ticket。
- `git diff --check`
- `uv run python scripts/release/public_projection.py plan --source WORKTREE --json`
- `uv run pytest tests/integration/test_release_to_main.py -q`

## Completion evidence

- Implementation commit: `c72b18814a29ffc83455c64a212fcf89fe807952` (`docs: rebuild work tracking governance`).
- Migration: `TODOS.md` now has only the five portfolio lanes, the single
  `GH-15` Next pointer, and triggered Roadmap options; stale completed,
  monitoring-only, and duplicated detail entries were removed.
- Ticket audit: all 11 `next-release` tickets and this ticket use stable
  `LOCAL-...-NN` IDs, separate `Status`/`Triage`/`Executor` fields, and the
  unified `resolved` terminal status with completion evidence. Their effort
  maps are tracked under `.scratch/`.
- Governance implementation: `scripts/check-work-governance.py`, public agent
  guidance, documentation indexes, and release projection assertions now
  enforce the model without contacting GitHub.
- Verification: `uv run python scripts/check-work-governance.py` passed; the
  public projection plan reported 425 public, 103 private, 2 generated, and
  427 candidate paths; focused governance/public-projection tests passed (13);
  `uv run pytest tests/integration/test_release_to_main.py -q` passed (18);
  full release preflight passed (658 Python tests, 115 UI tests, UI lint/build,
  wheel/sdist allowlists, and version consistency); both `git diff --check`
  modes passed.
- Follow-up: `GH-15` open/closed state still requires human triage; no GitHub
  write or Next.js upgrade was performed.
