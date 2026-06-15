---
title: Phase 3 Implementation Plan
codename: reproducible_sandbox.v1
status: completed
author: micro-eval
date: 2026-06-14
authority: docs/superpowers/specs/2026-06-02-unicorn-design.md (Part I), docs/engineering/security-guidelines.md
supersedes_framing: CLAUDE.md / TODOS "Docker sandbox" wording — see §0.
---

# Phase 3 Implementation Plan: `reproducible_sandbox.v1`

> 沿用 `2026-06-12-phase2-implementation-plan.md` 的结构。每个里程碑给出：规格依据 / 文件清单 / 核心契约 / 实施步骤 / 验收标准。底座**串行接入**，不并行做完。

## 0. 方向更正（动手前必读）

CLAUDE.md 路线图与 TODOS 用 **"Docker sandbox"** 描述 Phase 3，但权威来源 `unicorn-design.md` §3.4.5（L963）已明确决策：**Level 3+ 隔离通过远程 Provider（E2B/Modal）实现，不使用本地 Docker**（Docker 启动慢、需 daemon、macOS 体验差；gVisor 仅 Linux）。

按 CLAUDE.md 硬规则"工程规范/路线图与权威来源冲突时以权威来源为准"，本计划以 spec 的 `WorkspaceProvider` 模型为准：

- **本地隔离**：Level 0 = GitWorktreeProvider（已交付），Level 1 = Seatbelt(macOS)/Bubblewrap(Linux) OS 策略。
- **远程隔离**：Level 3–4 = E2BProvider/ModalProvider（远程，untrusted/adversarial）。
- **不引入本地 Docker / Podman / gVisor 作为 MVP 隔离手段。**

> **行动项**：合入本计划前，更新 CLAUDE.md 与 TODOS 的 "Docker sandbox" 措辞为 "provider-based sandbox（本地 OS 策略 + 远程 provider）"，使路线图与 spec 一致。

## 1. 范围与接入顺序

Phase 3 目标（spec §3.4、§5.5、Decision 成熟度表 L395）：可复现的多级隔离执行 + 更复杂 workspace 类型 + 趋势分析。串行接入顺序：

1. **P3-a**：`WorkspaceProvider` 抽象 + Level 0 重构（把现有 worktree 逻辑收敛为 `GitWorktreeProvider`）+ 隔离/信任维度进数据模型与 SameStartSnapshot。**纯重构 + 模型扩展，零行为变化，先立地基。**
2. **P3-b**：本地 Level 1 OS 策略 provider（Seatbelt/Bubblewrap），不可用时降级到 Level 0 并记 caveat。
3. **P3-c**：远程 Level 3–4 provider（E2B/Modal），可选、secrets 严格、未配置时不可用而非报错。
4. **P3-d**：更复杂 workspace 类型（多源 fixture + digest、toolchain/dependency 指纹进快照）。
5. **P3-e**：趋势分析（跨 run），触发 JSON→SQLite 存储迁移（当前 Blocked 项的解除条件）。

### Phase 3 明确不含（登记备查，防止范围蔓延）

- 本地 Docker/Podman/gVisor 隔离（见 §0，spec 决策不做）。
- 第三方 provider entry-points 注册（spec §3.4.4 标注 deferred，非本阶段）。
- RBAC/SSO、多团队协作、blind comparison、Elo/pairwise ranking（spec §MVP 不含，且非 Phase 3）。
- 自动 task 生成、在线服务威胁模型。

## 2. 模块升级总表

| 模块 | 现状（Phase 2 后） | Phase 3 升级 | 里程碑 |
|------|-------------------|-------------|--------|
| `engine/workspace.py` | 直接实现 worktree/blank/files + snapshot | 抽出 `WorkspaceProvider` Protocol；现逻辑→`GitWorktreeProvider` | P3-a |
| `engine/providers/` (新) | — | `git_worktree.py`、`os_policy.py`(Seatbelt/Bubblewrap)、`remote.py`(E2B/Modal) | P3-a/b/c |
| `models/task.py` `WorkspaceSpec` | type/path/files/setup/ref | + `isolation_level`、`trust_level`、`network_policy` | P3-a |
| `models/environment.py` `SameStartSnapshot` | workspace/commit/digests | + `sandbox_policy`、`network_policy`、`toolchain_fingerprint`（可比性维度） | P3-a/d |
| `engine/kernel.py` | 调 WorkspaceManager | 经 provider registry 选 provider；隔离不一致进 caveat | P3-a/b |
| `store/` | JSON 文件 | 趋势查询触发 SQLite 迁移层（保留 JSON 读写兼容） | P3-e |
| `decision/` | 单 run 决策 + 基础统计 | 跨 run 趋势聚合（confidence/recommendation 成熟度） | P3-e |
| UI | 对比/复盘/报告页 | 趋势页（跨 run 折线 + 回归检测） | P3-e |

## P3-a：WorkspaceProvider 抽象 + Level 0 重构 + 隔离维度入模型

### 规格依据
spec §3.4.4（Provider Protocol）、§3.4.5（内置 provider 层级）、§3.4.3（信任等级 boundaries）、§5.5（environment 进快照）。Principle 3「Environment is part of input」、Principle 11「能力挂模块不新增架构」。

### 文件清单
- 新 `src/micro_eval/engine/providers/__init__.py`、`base.py`（Protocol + 数据类）、`git_worktree.py`。
- 改 `src/micro_eval/engine/workspace.py`（保留 `WorkspaceManager` 外观，内部委托 provider；`_assert_within_root` 等边界守卫保留）。
- 改 `src/micro_eval/models/task.py`（`WorkspaceSpec` 加 `isolation_level: IsolationLevel = "logical"`、`trust_level: TrustLevel = "trusted"`、`network_policy: NetworkPolicy | None`）。
- 改 `src/micro_eval/models/environment.py`（`SameStartSnapshot` 加 `sandbox_policy`、`network_policy`）。
- zod 同步 `ui/src/lib/schema.ts`；golden 经 `scripts/generate-golden.py` 重生成。

### 核心契约（实现时以此为准）
```python
# engine/providers/base.py
class WorkspaceProvider(Protocol):
    name: str
    supported_levels: list[IsolationLevel]
    async def create(self, spec: WorkspaceSpec) -> WorkspaceHandle: ...
    async def exec_command(self, handle: WorkspaceHandle, argv: list[str],
                           env: dict[str, str] | None = None) -> CommandResult: ...
    async def collect_artifacts(self, handle: WorkspaceHandle) -> list[Artifact]: ...
    async def collect_diff(self, handle: WorkspaceHandle) -> str | None: ...
    async def snapshot(self, handle: WorkspaceHandle) -> str: ...
    async def restore(self, handle: WorkspaceHandle, snap: str) -> None: ...
    async def cleanup(self, handle: WorkspaceHandle) -> None: ...
```
- 签名与 spec §3.4.4 一致：`exec_command` 接收 **argv list**（spec §3.4.4 已据锁定决策从 `cmd: str` 更新为 `argv: list[str]`，禁止 shell 字符串插值）；`collect_artifacts` 返回已封装的 `Artifact`（含 ref/manifest/redaction 边界），**不返回裸 `Path`**，避免绕过 artifact 边界。
- provider registry 按 `spec.isolation_level` 选 provider；选不到则 fail-hard，但 P3-b/c 的"provider 不可用"降级见各自里程碑。

### 实施步骤
1. 定义 `IsolationLevel`/`TrustLevel`/`NetworkPolicy` 枚举与 `WorkspaceHandle`、`CommandResult` 数据类（对齐 spec §3.4.3 boundaries 字段）。
2. 抽 Protocol；把 `workspace.py` 现有 worktree/blank/files + snapshot 逻辑搬入 `GitWorktreeProvider`（行为不变，`supported_levels=[logical]`）。
3. `WorkspaceManager` 改为 registry 外观，默认注册 `GitWorktreeProvider`；保留现有公共方法签名与边界守卫。
4. 模型加字段（向后兼容默认值）；zod + golden 同步。
5. 隔离/network policy 进 `SameStartSnapshot`，作为 P0-b 可比性 gate 的新维度（不同 sandbox/network = 起点不一致 → caveat）。

### 验收标准
- 现有全部执行 e2e（test_p0a/p0b/phase2_golden）零行为变化通过。
- 新增 provider 协议契约测试：GitWorktreeProvider 满足 Protocol；registry 选择正确。
- 跨语言契约：新字段双端一致（pytest golden round-trip + vitest assertNoStrippedKeys）。
- 安全：`exec_command` argv-only 的负向测试（拒绝 shell 串）。

## P3-b：本地 Level 1 OS 策略 provider（Seatbelt / Bubblewrap）

### 规格依据
spec §3.4.5（SeatbeltProvider macOS / BubblewrapProvider Linux = Level 1 semi_trusted）、§3.4.3 `semi_trusted` boundaries（filesystem workspace_only、network allowlist、resources timeout/memory）。

### 文件清单
- 新 `src/micro_eval/engine/providers/os_policy.py`（`SeatbeltProvider`、`BubblewrapProvider`）。
- 改 registry：按平台 + 可用性注册。
- 改 `engine/kernel.py`：provider 不可用时降级 Level 0 + caveat。

### 核心契约
- `SeatbeltProvider` 用 `sandbox-exec` 生成 profile（filesystem 限定 workspace、network allowlist）；`BubblewrapProvider` 用 `bwrap` 挂载只读根 + 可写 workspace + `--unshare-net` 或 allowlist。
- **可用性探测**：二进制不存在/平台不符时 `supported_levels` 不含 os_policy；kernel 请求 Level 1 但无 provider → 降级 Level 0，`SameStartSnapshot.caveats` 记 `"requested isolation os_policy unavailable on <platform>; ran at logical"`（fail-soft，可解释优先 P4）。

### 实施步骤
1. 实现两个 provider 的 create/exec_command/cleanup（snapshot/restore 对 Level 1 可 NotImplemented 或退化为 worktree commit）。
2. resource limits（timeout/memory）经 OS 机制施加；超限分类为新的失败模式（与 #9 错误分类对齐，spec 先行）。
3. network allowlist：记录到 `network_policy` 进快照（可比性维度）。
4. 降级路径 + caveat。

### 验收标准
- macOS 上 Seatbelt 实测：workspace 外写入被拒（负向测试）；network allowlist 生效。
- Linux 上 Bubblewrap 同等负向测试。
- 平台不支持时降级 Level 0 且 caveat 出现（不崩溃）。
- 安全：逐条过 security-guidelines「workspace 边界 / network 边界 / secrets」。

## P3-c：远程 Level 3–4 provider（E2B / Modal，可选）

### 规格依据
spec §3.4.5（E2B/Modal = Level 3-4 untrusted/adversarial，远程）、§3.4.3 `untrusted`/`adversarial` boundaries（network allowlist/none、snapshot_restore lifecycle）。profile `remote_untrusted.v1`（spec §profiles）。

### 文件清单
- 新 `src/micro_eval/engine/providers/remote.py`（`E2BProvider`、`ModalProvider`）。
- secrets 通道复用 `MICRO_EVAL_SECRET_*` + Redactor；远程凭证经 `required_secrets` 声明。

### 核心契约
- 精确映射（spec §3.4.4 内置 provider 表 L946-947）：`ModalProvider` = container = Level 3 = `untrusted`（`supported_levels=["container"]`）；`E2BProvider` = vm = Level 4 = `adversarial`（`supported_levels=["vm"]`，network=none、snapshot_restore）。registry 按 `trust_level` 选对应 provider。
- 未配置远程凭证时 provider `supported_levels` 为空 → 请求 untrusted/adversarial 但无 provider → **fail-hard 并给出清晰错误**（不静默降级到本地，因为信任等级降级会让 untrusted 代码在本地执行，安全不可接受）。
- `snapshot/restore` 对 adversarial（vm）用 provider 原生快照；network=none。
- 所有上传/下载 artifact 经 Redactor；远程 stdout/stderr 截断 cap 与本地一致。

### 实施步骤
1. E2B/Modal SDK 适配层（保留适配层吸收底座变化，沿用架构约束 1）。
2. 凭证经 secrets 通道；缺失时 supported_levels 空。
3. artifact/diff 回收 + redaction；远程 cost 经 trace 适配层（与 Phase 2 cost ladder 衔接）。

### 验收标准
- 有凭证时端到端跑通一个远程 cell（集成测试，CI 跳过/标记）。
- 无凭证时请求远程隔离 → 清晰失败、不降级、不泄漏（负向测试）。
- 安全：远程边界、secrets redaction、network policy 三项过 checklist。

## P3-d：更复杂 workspace 类型

### 规格依据
spec §5.5（fixture digest、toolchain/dependency fingerprint 进快照作为可比性维度）、Gate 输入清单 L364。

### 文件清单
- 改 `models/task.py` `WorkspaceSpec`（多源 fixture + 每源 digest；可选 toolchain 声明）。
- 改 `engine/workspace.py`/provider（多源准备 + 指纹采集）。
- 改 `models/environment.py`（`toolchain_fingerprint`、`fixture_digests` 进 SameStartSnapshot）。

### 核心契约
- 每个 workspace 源记录 sha256 digest；toolchain（python/node 版本、lockfile hash）指纹进快照。
- 这些是**可比性维度**：baseline/candidate 指纹不一致 → 起点不一致 caveat。
- 复用 P3-a 的 `_assert_within_root` 边界（多源同样不得越界）。

### 验收标准
- 多源 fixture workspace 准备 + digest 记录正确。
- 指纹进快照并参与 P0-b gate；不一致出 caveat。
- 跨语言契约同步。

## P3-e：趋势分析 + JSON→SQLite 迁移

### 规格依据
spec Decision 成熟度表 L395（`trends / confidence / recommendations`）、§5.5；TODOS Blocked「JSON→SQLite 迁移」解除条件 = 跨 run 查询需求（趋势分析触发）。

### 文件清单
- 新 `src/micro_eval/store/sqlite_store.py`（schema_version 已预留；保留 JSON 读写兼容/导入）。
- 改 UI API routes：不再直接读 `.micro-eval/` JSON，改经 store 抽象（spec 注明的迁移同步点）。
- 新趋势聚合 `decision/trend.py`；新 UI 趋势页。

### 核心契约
- SQLite 为跨 run 查询索引；run 详情仍可由 JSON 重建（可复现/可溯源不丢）。
- 趋势 = 同 configuration id 跨 run 的 pass_rate/cost/latency 序列；**复用 #2 的 `configuration_drift_caveats`**：内容漂移的 run 在趋势线上标注"不可比"断点，避免把不同实现的指标连成误导性趋势。
- 趋势结论仍受 P4 可解释约束：每个点可回溯到具体 run/decision。

### 实施步骤
1. SQLite schema + 从 JSON 双向迁移/导入；run_store/artifact_store 抽象统一入口。
2. UI 数据读取层改经 API（不再直读 JSON 文件）。
3. 趋势聚合 + drift 断点标注；趋势页（折线 + 回归检测 + caveat）。

### 验收标准
- 既有 JSON run 可导入 SQLite 并读出，决策/溯源一致（回归保护）。
- 趋势页正确标注 config 漂移断点（#2 集成）。
- legacy 兼容与跨语言契约不破。

## 3. 统一交付门槛（每个里程碑）

沿用 Phase 2：每个里程碑合并前必须满足——
1. 功能验收（上述各 verdict）+ 全套 pytest/vitest 绿、覆盖率 ≥ CI 门禁。
2. **安全验收**：执行链路改动（subprocess/env/stdout 捕获/artifact 持久化/workspace 写入/网络边界）逐条过 `docs/engineering/security-guidelines.md` 末尾 Code Review Checklist；交付报告说明 secrets redaction、workspace 边界、shell interpolation、**network 边界**四项。安全验收与功能验收同为合并门槛。可机械验证的 shell 插值门禁（沿用 Phase 2，零匹配）：
   ```
   grep -RInE 'create_subprocess_shell|shell=True' src tests ui examples
   ```
   远程 provider exec 同样必须 argv-only，不得拼 shell 字符串。
3. 跨语言契约：新 schema 字段经 `scripts/generate-golden.py` 单源生成，pytest + vitest 双端守护。
4. 子 agent 独立评审通过、版本号 bump、CHANGELOG/README/TODOS/CLAUDE 同步。

## 4. 风险登记

| 风险 | 缓解 |
|------|------|
| 远程 provider 信任降级（untrusted 代码落本地执行） | P3-c fail-hard，不静默降级；只有 Level 0↔1 可降级 |
| OS 策略 provider 平台差异（Seatbelt/Bubblewrap 行为不一致） | 各自负向测试；不可用时降级 Level 0 + caveat |
| sandbox 启动开销影响并行吞吐 | 沿用 asyncio 并行 + max_concurrency；远程 provider 池化（后续） |
| SQLite 迁移破坏 legacy JSON 兼容 | 双向导入 + legacy 读路径回归测试；run 详情仍可由 JSON 重建 |
| 趋势线把不可比 run 连成误导结论 | 复用 #2 drift caveat，趋势线标注断点 |
| spec 与路线图"Docker"措辞冲突遗留 | §0 行动项：合入前更新 CLAUDE.md/TODOS 措辞 |

## 5. 与既有交付的衔接

- Level 0 = 现 `git worktree`（Phase 1）；本计划 P3-a 仅重构收敛，不改行为。
- cost ladder：远程 provider 的 cost 经 Phase 2 trace 适配层上报（cost ladder 第 2–3 级）。
- 可比性：隔离/network/toolchain 全部进 `SameStartSnapshot`，复用 P0-b gate 与 #2 漂移检测。
- 执行唯一 spawner 仍是 adapter/provider（由 `tests/contract/test_execution_contract.py` 守护，远程 provider 经适配层调用不破坏该契约）。
