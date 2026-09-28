---
title: micro-eval 发布流程
language: zh-CN
agent_read: false
authoritative: docs/engineering/release-process.md
doc_type: reference
status: active
created_at: 2026-06-03T13:09+08:00
updated_at: 2026-09-28T12:23+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - engineering
  - release
  - versioning
related:
  - AGENTS.md
  - docs/agents/issue-tracker.md
  - CHANGELOG.md
  - VERSION
  - docs/DEVELOPMENT.zh-CN.md
  - docs/documentation-standard.md
  - docs/engineering/security-guidelines.zh-CN.md
  - docs/releases/2026-07-02-release-backfill-record.md
  - scripts/release-to-main.sh
---

# micro-eval 发布流程

> **翻译参考，非权威版本。** 本文件是 [release-process.md](release-process.md) 的中文翻译，仅供人类阅读。
> 规范以英文原版为准；两者不一致时一律以英文版为准。Agent 与自动化流程必须阅读英文原版，不要读取本文件。

本文档是面向人类的发布参考。发布脚本位于仓库 `scripts/release/*` 与 `scripts/release-to-main.sh`（单一副本，双分支共同跟踪）。开发环境还提供可执行的发布清单 skill；若该 skill 与本文档不一致，必须在同一次变更中同时修正。公共发布的使用者应使用仓库脚本与本参考，二者不依赖私有开发记录。

## 目标

- 让发布工作可重复、可审计。
- 保持 `VERSION`、包元数据、运行时元数据、UI 包元数据与 run evidence 一致。
- 可执行发布自动化保持在 `scripts/release/` 与 `scripts/release-to-main.sh` 内。
- 发布前记录 release evidence 与依赖清单。
- 只从干净的 `dev` checkout 经既有投影脚本发布 `main`。
- 让 `scripts/release/public-projection.toml` 成为唯一的路径分类 source of truth。
- 每个新的公开发布提交只连接前一个公共 `main` 提交；`dev` 仅提供文件，不带入其提交历史。
- 本地投影保持为默认动作；更新 `origin/main` 之前必须单独执行 verified-SHA 的 push 动作。
- 公共 remote 不含 `dev`；公共仓库没有私有分支。
- 私有开发 remote 启用后，日常私有集成走 `private/dev` Pull Request；这不改变公共投影或发布接口。
- 所有候选测试、构建与工件门通过后才移动本地 `main`。
- 避免把 secrets 或运行时产物泄漏进发布文档或提交。

## 发布边界

- 日常开发在 `dev`。
- `dev` 保持本地或放在独立私有 remote 上。公共仓库内的分支即使不是默认分支也是公开的。
- `origin` 是公共 remote，不得接收 `dev`、`agent/*`、`human/*` refs。私有 remote 名为 `private`；其身份与凭据是开发侧信息，不得写入公共文档。
- 已启用的 `private/dev` 上的非紧急变更通过 Pull Request 与独立审查集成。`main` 不是日常 Pull Request 目标：它保持为由 `scripts/release-to-main.sh` 生成的发布投影。
- 公共 GitHub CI 在投影后的 `main` 与公共 pull request 上运行；不需要把私有 `dev` 推到公共仓库。
- 不要为发布手动把当前 worktree 切到 `main`。
- 只用发布脚本 stage 本地 `main`。该单命令 stage 仅本地执行，绝不接触 remote：

```bash
scripts/release-to-main.sh stage dev main
```

等价的显式写法是：

```bash
scripts/release-to-main.sh --local-only dev main
```

`--no-push` 是 `--local-only` 的别名。本地投影会打印 verified 完整 SHA。只有在明确授权后，才可在单独动作中发布该确切 SHA：

```bash
scripts/release-to-main.sh publish --expected-sha <FULL_VERIFIED_SHA> dev main
```

publish 动作拒绝缺失、未验证、过期、缩写或非 `main` 的 SHA，且当公共 remote 含有 `dev` 时中止。它会在运行 Git 前显示 `origin/main` 与确切提交。

如果 `main` 与发布 tag 都被明确批准，用一次原子远端更新同时发布：

```bash
scripts/release-to-main.sh publish --expected-sha <FULL_VERIFIED_SHA> \
  --tag vX.Y.Z dev main
```

tag 必须是 annotated、等于 `v` 加 receipt 中记录的发布版本号，并指向与 `main` 相同的 verified 提交。绝不向公共 remote 推送 `dev`、`--all` 或 `--mirror`。

## 公共投影策略

`scripts/release/public-projection.toml` 对每个 tracked 源路径分类：

- `public`：从已提交的 `dev` SHA 恢复进候选树；
- `private`：保留在 `dev`，绝不恢复进 `main`；
- `generated`：由显式 source/target 映射写入。

匹配到零个或多个分类的路径将中止发布。已知敏感路径与私钥标记是附加的拒绝检查，不是发布的 source of truth。投影实现位于 `scripts/release/public_projection.py`，通过发布脚本与测试共用的同一接口执行。

该模块在隔离 worktree 中从空 index 构建候选树。它从发布 skill 资产生成 `AGENTS.md`，从 `scripts/release/main.gitignore` 生成 `.gitignore`。验证时，逐项对比候选路径、blob、文件模式和生成文件与固定源提交的投影结果。从候选树删除文件，不会删除早期提交里的同一文件。

每个新候选恰好只有一个父提交：前一个公共 `main` 提交。已提交的 `dev` SHA 提供文件内容，并作为来源元数据记录；它不会成为合并父提交。策略中的 `[history].public_base_sha` 标识已批准的公共历史边界。stage、验证与 publish 都检查此边界之后的实际历史：所有提交必须构成一条单父链，每个提交的树只能包含允许的公共或生成路径，并通过内容及符号链接检查。浅历史、replacement refs 和 grafts 不能替代这项证明。

即使最新文件树干净，只要目标分支的历史结构或历史内容不符合要求，stage 也会拒绝。普通发布命令不会改写已有历史。历史检查失败时，必须先完成另行审查的维护工作，才能恢复正常发布；仅安装新发布器不代表旧历史已经清理完毕。

候选构建写入第 2 版本地 receipt，记录 `projection_mode: single-parent` 和 `staged` 状态，不移动 `main`。receipt 绑定源与候选 SHA、候选树、策略 digest、发布版本、前一个目标提交、历史边界及发布起点。候选的 Python/UI 测试、构建、敏感路径检查与 wheel/sdist 校验全部通过后，验证步骤以原子 compare-and-swap 更新本地 `main` 并把 receipt 标记为 `verified`。候选失败时 `main` 保持不变。publish 成功后，receipt 标记为 `published`。

源提交、策略和目标均未变化时，重复 stage 会重新验证并复用候选 SHA，包括已验证或已发布的候选；不会把 `published` 降回 `verified`。旧版 receipt 会被拒绝，不会隐式升级。不得手工修改 receipt 来绕过历史验证。

## 版本源策略

`VERSION` 是唯一由人编辑的发布版本源。

Python 包应通过 Hatch dynamic version 元数据从 `VERSION` 读取构建版本：

```toml
[project]
dynamic = ["version"]

[tool.hatch.version]
path = "VERSION"
pattern = "^(?P<version>.+)$"
```

发布流程必须确保以下"当前版本"表面一致：

- `VERSION`
- 构建出的 Python 包元数据与 dist 工件名
- Python 运行时 `micro_eval.__version__`
- `ReplayCanonical.tool_version`
- 顶层 `README.md` 当前版本
- `ui/package.json`
- `ui/package-lock.json` 根包元数据
- 包含当前 `tool_version` 的共享 contract fixtures

`CHANGELOG.md`、dev log、归档文档与 spec 中的历史发布引用不得批量替换。它们描述过去状态。

## 必需的发布输入

准备发布前，明确：

- 目标版本，遵循 SemVer。
- 发布类型：patch、minor、major 或 prerelease。
- 面向用户的变更，供 `CHANGELOG.md`。
- 验证范围与已知风险。
- 是否为 verified SHA 原子发布 annotated `vX.Y.Z` tag。
- 是否允许推送分支/tag。默认：未明确确认不推送。

## 版本号更新流程

1. 运行版本预检审计：

```bash
scripts/release/check-version-consistency.py --version "$(cat VERSION)"
```

2. 需要时同步新版本：

```bash
scripts/release/sync-version.py X.Y.Z
```

3. 重跑一致性检查。
4. 构建包并确认 dist 工件名包含目标版本。
5. 确认 run plan 写入的 `ReplayCanonical.tool_version` 等于目标版本。

## Changelog 流程

使用 Keep a Changelog 风格的小节：

- `Added`
- `Changed`
- `Fixed`
- `Security`
- `Verification`
- `Known Gaps`

只记录面向用户或面向发布的变更。不要把 `CHANGELOG.md` 当实现日记。

## Dev log 流程

发布准备或发布流程变更必须写开发日志：

```text
docs/dev/log/YYYY-MM-DD-HHMM-dev-log-<topic>.md
```

文件名必须包含 `dev-log`，文档必须遵守 `docs/documentation-standard.md` 的元数据规则。

## README 流程

发布前检查 `README.md` 反映：

- 当前版本。
- 安装/源码 checkout 路径。
- 当前 CLI 命令。
- 适用时的开箱即用示例入口。
- 适用时的 UI 与 wheel/源码注意事项。

详细发布机制保留在本文档，不放进 README。

## 依赖清单流程

每次发布应在 `docs/releases/` 下生成人类可读与机器可读的依赖清单：

```text
docs/releases/YYYY-MM-DD-vX.Y.Z-dependency-inventory.md
docs/releases/YYYY-MM-DD-vX.Y.Z-dependency-inventory.json
```

清单应包含：

- Python 运行时版本。
- `uv` 版本。
- `pyproject.toml` 的 Python 包元数据。
- 运行依赖、可选依赖、依赖组，以及 `uv.lock` 解析出的包名/版本。
- 可获取时的 Node 与 npm 版本。
- UI `package.json` 的 dependencies/devDependencies。
- UI `package-lock.json` 根元数据与解析出的包名/版本。
- 示例所需的外部 agent CLI 前置条件，以尽力而为的工具可用性/版本检查记录，不读取 secrets。

不得记录环境变量、token、账号标识、可执行文件绝对路径、home 目录路径或本地凭据路径。

## Release evidence 流程

每次发布应写：

```text
docs/releases/YYYY-MM-DD-vX.Y.Z-release-evidence.md
```

release evidence 应包含：

- 版本与日期。
- 源分支与目标分支。
- 依赖清单链接。
- 构建工件名与 SHA256 哈希。
- 验证命令与结果。
- 执行过的 code review / architecture review 状态。
- 执行过的 UltraQA 或对抗性 smoke 状态。
- 已知 caveat。
- `scripts/release-to-main.sh stage dev main` 之后的主投影验证。

## 预检验证矩阵

按改动文件运行合适的发布检查。发布工作的默认门是：

```bash
scripts/release/check-version-consistency.py --version "$(cat VERSION)"
scripts/release/preflight-release.sh "$(cat VERSION)"
```

preflight 对当前 worktree 分类、以显式 Hatch 输入构建 wheel/sdist，并按工件白名单逐项校验归档条目。未知、绝对、穿越或链接的归档条目使发布失败。

面向安全的 grep 必须检查可信路径没有引入 shell 子进程执行：

```bash
if grep -RInE 'create_subprocess_shell|shell=True' --exclude='test_execution_contract.py' src tests ui/src examples; then
  echo 'Forbidden shell subprocess pattern found' >&2
  exit 1
fi
```

浏览器存储 grep 是审查信号而非无条件失败；对任何命中按当前产品安全规则检查。

## 提交到 dev

提交前：

1. 确认当前分支是 `dev`。
2. 确认没有多余运行时产物被 staged 或 untracked。
3. 确认 release evidence 与依赖清单存在。
4. 运行验证矩阵。
5. 用英文提交信息提交，例如：

```bash
git commit -m "Prepare vX.Y.Z release"
```

## 把 dev 投影到 main

从干净的 `dev` 工作树执行单命令本地 stage：

```bash
scripts/release-to-main.sh stage dev main
```

运行前可用 `scripts/release-to-main.sh --help` 查看行为。stage 绝不切换活动 `dev` worktree、绝不接触 remote。它先执行完整发布预检，在隔离 worktree 构建候选树，对公共树重跑 Python/UI 门，从该树构建 wheel/sdist 并校验其内容，然后原子移动本地 `main`，并在 Git common directory 下保存 verified receipt。任何门失败都保持本地 `main` 不变。

审阅打印的完整 SHA。当且仅当用户授权更新 `origin/main` 时，用该确切值执行单独的 publish 动作：

```bash
scripts/release-to-main.sh publish --expected-sha <FULL_VERIFIED_SHA> dev main
```

该命令重新检查本地 `main` 等于该 SHA、第 2 版 receipt 为 `verified` 或已为 `published`、其固定源投影与策略 digest 仍匹配、公共历史有效，且公共 `origin` 不含 `dev`。然后先输出 `Push target: origin/main` 与 `Verified commit: <SHA>`，再只推送 `<SHA>:refs/heads/main`。发布 `main` 的授权不包含 tag，除非同时显式给出 `--tag vX.Y.Z`。

可以先完成多次本地 stage，再执行 publish。每次 stage 在前一个本地 `main` 上增加经过验证的公共提交；成功发布之前，这些 receipt 保留同一个发布起点（`publication_base_sha`）。发布最新的本地 verified SHA，就会发送这一段公共提交链。成功发布后，下次 stage 以刚发布的提交作为新的发布起点。

远端 `main` 必须仍等于 receipt 的发布起点；幂等重试时，也允许它已经等于确切候选。远端目标缺失、向前推进、分叉或回退都会中止发布。push 会检查本次操作由远端通告的 ref，并采用普通的原子非强制更新，关闭自动跟随 tag。远端出现意外变化时，应先核对并处理再重试；发布器不会强制把它退回记录值。

## 原子 tag 流程

活动 worktree 仍在 `dev` 时不要运行无限定的 `git tag`；那可能给私有开发提交打 tag。如果用户明确批准公共分支与 tag，使用 verified 发布接口：

```bash
scripts/release-to-main.sh publish --expected-sha <FULL_VERIFIED_SHA> \
  --tag vX.Y.Z dev main
```

该 Module 为确切的 verified SHA 创建或校验 annotated tag，并使用 `git push --atomic`，使远端 `main` 与 tag 要么一起更新、要么都不更新。

## 中止条件

出现以下任一情况时中止发布并修复原因：

- 版本表面不一致。
- 构建工件版本与 `VERSION` 不一致。
- 缺少 release evidence 或依赖清单。
- 安全 grep 在可信路径发现 shell 子进程执行。
- 测试或构建失败。
- 候选门失败；本地 `main` 必须保持原 SHA。
- `scripts/release-to-main.sh` 前 `dev` 工作树不干净。
- `main` 投影仍跟踪 dev-only 文档。
- tracked 路径未知、多重分类或禁止出现在公共输出。
- wheel/sdist 条目超出工件白名单。
- 本地 `main` 树与策略派生的候选树不同。
- 缺少已批准的公共历史边界，或边界后的提交存在多父结构、禁止的路径/内容，或历史无法验证。
- 期望推送的 SHA 缺少当前第 2 版 `verified` 或 `published` receipt；旧版 receipt 不被接受。
- 远端 `main` 既不等于记录的发布起点，也不等于确切候选，或远端 ref 在发布期间发生变化。
- 公共 remote 含有 `dev`，或请求的 tag 不是同一 verified SHA 的 annotated 版本 tag。
- 在无明确授权的情况下选择了 `--push`；使用默认 local-only 模式。
- 发布文档或 staged 变更中存在 secrets、凭据路径或运行时产物。
