---
title: "CI Pipeline 与 Contract Golden 机制实施计划"
doc_type: spec
status: completed
created_at: 2026-06-12T21:30+08:00
updated_at: 2026-06-12T22:30+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - ci
  - contract-testing
  - golden-fixtures
  - infrastructure
related:
  - docs/superpowers/specs/2026-06-02-test-architecture.md
  - docs/superpowers/plans/2026-06-12-phase2-implementation-plan.md
  - docs/engineering/testing-guidelines.md
---

# CI Pipeline 与 Contract Golden 机制实施计划

> **交付状态（2026-06-12，v0.2.2）**：两个切片均已交付。pytest 147 passed
> （覆盖 77.8%，门禁 75%）、vitest 41 passed。两个漂移注入实验均实测变红：
> 生成器加字段未提交 golden → golden-sync diff exit 1；golden 含新字段而
> zod 未声明 → strict 检查报 "zod silently stripped these fields"。
> 实施中对计划的一处加固：golden-sync 改用 `git add -A` + `git diff --cached`，
> 否则新增的 golden 文件（untracked）会被 `git diff` 静默放过。

> **执行说明**：遵循项目硬规则——禁止 TDD；spec 先行（本计划落地前，
> 若与 `2026-06-02-test-architecture.md` 冲突，先改该 spec）。
> 安全验收与功能验收同为合并门槛。

**目标**：兑现 test-architecture §4（跨语言 golden 契约）与 §7（CI 与覆盖率
门槛）两节纸面规划，使 122 + 18 个测试的回归保护从「谁记得跑」变为强制门禁。
目标版本 0.2.2。

**为什么现在做**：Phase 3 将改动执行链路（Docker sandbox、复杂 workspace），
v0.2.1 补齐的所有测试防线只在本地生效；没有 CI，防线等于不存在。

---

## 1. 范围

### 做

1. GitHub Actions CI pipeline（PR + push 到 dev/main 触发）。
2. `tests/contract/` golden 机制：Pydantic 自动生成 golden JSON，
   pytest 与 vitest 双端消费，漂移即红。
3. `pytest-cov` 入 dev 依赖；覆盖率门槛与防倒退检查。
4. 现有散点契约测试（`test_contract_fixture.py`、ui fixtures 手工维护）
   迁移到 golden 机制，消除手工同步。

### 不做（登记备查）

- 发布自动化（release-to-main 仍走本地 skill 流程，含人工审批点）。
- CD / 部署（本产品是本地工具，无部署面）。
- 真实 LLM / Langfuse 的 nightly integration job（§6 已定义
  `@pytest.mark.llm_integration` 挂载点，等真实使用场景出现再启用）。
- Windows runner（目标用户环境为 macOS/Linux；Windows 兼容性由
  `run-example.py` 的跨平台设计兜底，不进 CI 矩阵）。

---

## 2. 设计决策

### 2.1 CI 平台与触发

| 决策 | 结论 | 理由 |
|------|------|------|
| 平台 | GitHub Actions | 仓库已在 GitHub；无自建 runner 需求 |
| 触发 | `pull_request` + `push`(dev, main) | dev 是日常开发分支，push 即验证 |
| Python | 3.11 + 3.12 矩阵 | requires-python >=3.11；3.12 提前暴露兼容问题 |
| Node | 20.x 单版本 | Next.js 本地 UI，无多版本诉求 |
| 缓存 | uv cache + npm cache | 控制 CI 时长（目标全流程 < 5 分钟） |

### 2.2 Job 拆分（对齐 test-architecture §7）

```yaml
jobs:
  python-tests:      # pytest 全量（unit + contract + e2e 目前同套件）
    run: uv run pytest -q --cov=micro_eval --cov-report=xml --cov-fail-under=75
  python-quality:    # 编译 + 安全 grep 门禁
    run: |
      uv run python -m compileall -q src/micro_eval tests
      grep -RInE 'create_subprocess_shell|shell=True' src tests ui/src examples && exit 1 || true
  golden-sync:       # golden 生成是幂等的：重新生成后 git diff 必须为空
    run: |
      uv run python scripts/generate-golden.py
      git diff --exit-code tests/contract/golden/
  ui-tests:          # vitest + lint + build
    run: |
      cd ui && npm ci && npm run lint && npx vitest run && npm run build
  example-smoke:     # 交付门槛第 4 条上 CI
    run: python examples/run-example.py
```

覆盖率门槛策略（兑现 §7 的「渐进启用」）：

- 起步 `--cov-fail-under=75`（当前实际 78%，留 3 个点缓冲避免脆性门禁）；
- 防倒退用「门槛只升不降」的人工约定代替 diff-coverage 服务（不引入
  Codecov 等外部依赖——本项目无 CI secrets 是有意的安全姿态，见 §5）；
- vitest 暂不设覆盖率阈值（§2 分层表已确认 UI 只做关键断言，不追覆盖率），
  以用例必须全绿为门槛。

### 2.3 Contract golden 机制

**现状问题**：`ui/src/lib/fixtures/*.json` 由人手工维护，Python 端
`test_contract_fixture.py` 只能事后校验「fixture 还能被 Pydantic 解析」，
不能保证 fixture 反映最新 schema（新增 optional 字段时双端都绿但 fixture
陈旧）。

**目标机制**（test-architecture §4 的兑现）：

```text
scripts/generate-golden.py（Pydantic 构造 + model_dump_json）
        │ 写入
        ▼
tests/contract/golden/*.json     ←── 提交进仓库（diff 可审）
        │ 消费                          │ 消费
        ▼                              ▼
tests/contract/test_golden.py    ui/src/lib/__tests__/golden-contract.test.ts
（Pydantic round-trip 校验）       （zod strict parse）
        ▲
        │ CI golden-sync job：重新生成后 git diff 必须为空
```

要点：

1. **生成器是唯一事实来源**：`scripts/generate-golden.py` 用 Pydantic 模型
   显式构造典型 + 边界实例（null 字段、空数组、各 enum 值——§4 要求的
   edge cases），确定性输出（固定时间戳与 id，禁止 `datetime.now()`）。
2. **golden 文件提交进仓库**：schema 变更时 PR diff 直接展示契约变化，
   评审者可见；CI `golden-sync` job 防止改了模型忘了重新生成。
3. **覆盖的 schema**（§4 清单）：`RunRecord`（含 Phase 2 字段全开与全空
   两个变体）、`DecisionReport`、`TraceRef`、`EvaluationResult`、
   `RunPlan`、legacy v0.1.x 变体（现 `tests/fixtures/legacy/` 并入）。
4. **vitest 端 strict parse**：用 zod `.strict()` 或解析后字段比对，
   确保「Python 多出的字段」也会被发现，而非被 zod 默认忽略——这是
   现有机制抓不到的漂移方向。
5. **迁移**：`ui/src/lib/fixtures/canonical-*.json` 与
   `tests/fixtures/legacy/` 的消费方改指向 `tests/contract/golden/`；
   vitest 通过相对路径读取（已验证 vitest 可读仓库内任意路径）。
   现有 fixture 文件在迁移完成后删除，避免双源。

### 2.4 文件清单

| 操作 | 路径 | 职责 |
|------|------|------|
| 新建 | `.github/workflows/ci.yml` | §2.2 五个 job |
| 新建 | `scripts/generate-golden.py` | golden 生成器（确定性） |
| 新建 | `tests/contract/golden/` | 生成的 golden JSON（提交） |
| 新建 | `tests/contract/test_golden.py` | Pydantic round-trip + 幂等校验 |
| 新建 | `ui/src/lib/__tests__/golden-contract.test.ts` | zod strict 消费 |
| 修改 | `pyproject.toml` | dev group 加 `pytest-cov` |
| 修改 | `tests/unit/test_contract_fixture.py` | 迁移/收编进 golden 机制 |
| 修改 | `ui/src/lib/__tests__/api-route-contract.test.ts`、`legacy-compat.test.ts` | fixture 路径切换 |
| 删除 | `ui/src/lib/fixtures/canonical-*.json`、`legacy-run-v01x.json` | 消除手工双源（迁移完成后） |
| 修改 | `docs/superpowers/specs/2026-06-02-test-architecture.md` | §4/§7 从「目标」改为「已实施」+ 实际命令 |

注意：`canonical-run-p0.json` 同时被 `check-version-consistency.py`
（tool_version 检查）引用，迁移时同步更新 release skill 脚本的路径。

---

## 3. 实施顺序（两个垂直切片）

1. **切片 A：CI 先行**（不依赖 golden 重构，立即获得保护）
   - `pytest-cov` 入依赖 → `.github/workflows/ci.yml` 五个 job
     （golden-sync 暂跑现有 `test_contract_fixture.py`）→ 本地
     `act` 或推送验证。
   - 完成标志：PR 上五个 job 全绿，故意改坏一个测试能见红。
2. **切片 B：golden 机制**
   - 生成器 → golden 文件 → 双端消费测试 → 迁移旧 fixture 消费方 →
     删除手工 fixture → CI golden-sync 切到真实幂等检查。
   - 完成标志：手动给 `RunRecord` 加一个字段不重新生成 golden，
     CI golden-sync 红；重新生成后 vitest strict parse 红（若 zod 未同步）。

## 4. 验收标准

- `uv run pytest -q` 全绿（含新 contract 测试）；vitest / lint / build 全绿。
- CI 在 PR 上运行五个 job 全绿；总时长 < 5 分钟。
- 漂移注入实验（两个方向各一次，结果记入 dev log）：
  - Pydantic 加字段不更新 golden → `golden-sync` 红；
  - golden 更新但 zod 未同步 → `golden-contract.test.ts` 红。
- 覆盖率门禁生效：`--cov-fail-under=75` 在人为删除测试时使 CI 红。
- 无双源：仓库内不存在与 golden 内容重复的手工 fixture。

## 5. 安全考量

- **CI 无 secrets**：所有测试无网络、mock LLM、fake Langfuse client，
  workflow 不配置任何 repository secret，`permissions: contents: read`
  最小化 token 权限。这是有意的安全姿态，也是不引入 Codecov 的原因之一。
- golden 生成器不得读取环境变量或真实 run 产物（防止本地路径/用户名
  泄入提交的 golden 文件）；生成内容过一次 `MICRO_EVAL_SECRET` /
  home-path grep 作为 `test_golden.py` 的断言。
- 按惯例过 security-guidelines Code Review Checklist 后方可合并。

## 6. 风险登记

| 风险 | 缓解 |
|------|------|
| golden 幂等检查因序列化顺序不稳定而 flaky | 生成器统一 `model_dump_json(indent=2)` + 固定字段顺序（Pydantic 默认按定义序）；幂等性本身是 test_golden.py 的用例 |
| zod strict 模式与现有宽松解析行为冲突 | 仅 golden 契约测试用 strict；运行时 API 解析保持现状（容忍未知字段是运行时韧性，契约测试才需要严格） |
| CI 时长膨胀 | uv/npm 缓存 + job 并行；example-smoke 是最慢项（~30s），可接受 |
| golden 与 release skill 的 fixture 引用断裂 | §2.4 已登记 check-version-consistency.py 同步项，验收时跑 release preflight 确认 |
