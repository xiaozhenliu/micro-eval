# AGENTS.md

This file is the stable boot context for agents working in this repository. Keep it short: rules that must be present every time stay here; detailed or change-prone guidance must live in the referenced source-of-truth documents.

## 必须始终遵守

- 始终用简体中文回复用户。
- git commit message 使用英文。
- 代码脚本中的注释使用英文。
- 禁止使用 TDD：不要采用“先写失败测试，再写实现让测试通过”的流程。
- 测试只用于验收、回归和契约保护，不能作为需求来源。
- 不要直接在 `main` 开发；日常开发在 `dev`。
- 安全规范始终适用；开发实现前必须阅读 `docs/engineering/security-guidelines.md`，并遵守其指向的具体安全规范。

## main 发布规则

`main` 是发布投影分支。不要在当前 dev 工作区执行 `git checkout main` 后手动发布。

发布必须从 dev 工作区运行：

```bash
scripts/release-to-main.sh dev main
```

`main` 不得跟踪以下 dev-only 内容：

- `docs/superpowers/`
- `docs/_archive/`
- `docs/references/`
- `docs/bug_reports/`
- `micro-eval-brd.md`
- `micro-eval-prd.md`

`main` 的 `AGENTS.md` / `CLAUDE.md` 只允许由发布模板生成；如需修改，先改项目级 release skill 内的模板：

- `.codex/skills/micro-eval-release/assets/templates/agents-publish-template.md`
- `.codex/skills/micro-eval-release/assets/templates/claude-publish-template.md`

完整可执行 release 流程以项目级 skill `.codex/skills/micro-eval-release/SKILL.md` 及其 bundled scripts/assets 为准；本节只保留不可违反的 main 发布边界。

发布后必须确认 main 没有跟踪 dev-only docs：

```bash
test -z "$(git ls-files 'docs/superpowers/*' 'docs/_archive/*' 'docs/references/*' 'docs/bug_reports/*')"
```

## 执行任务前的行动路由

开始实现前，先判断任务类型，并读取对应依据；不要仅凭本文件推断产品、架构、schema、测试、命令或文档格式细节。

- 不确定文档位置或用途 → 先读 `docs/README.md`。
- 需要本地开发命令、验证方式、模块入口 → 读 `docs/DEVELOPMENT.md`。
- 涉及文档新增、移动、metadata、时间戳、目录归属 → 读 `docs/documentation-standard.md`。
- 涉及产品范围、MVP 边界、用户路径 → 读 `docs/superpowers/specs/2026-06-02-mvp-profile.md`。
- 涉及长期架构边界、分层、模块职责 → 读 `docs/superpowers/specs/2026-06-02-unicorn-design.md`。
- 涉及测试体系、测试类型、contract/e2e 策略 → 读 `docs/superpowers/specs/2026-06-02-test-architecture.md`。
- 涉及发布验证或 release gate → 读/写 `docs/releases/`。
- 涉及版本号、CHANGELOG、release evidence、依赖清单、发布提交、tag 或 dev→main 发布 → 使用项目级 skill `.codex/skills/micro-eval-release/SKILL.md`；该 skill 内的 bundled scripts/assets 是 release 可执行流程来源。
- 涉及开发过程记录 → 写入 `docs/dev/log/`。

工程任务只读取命中的工程规范，不要默认读取整个 `docs/engineering/`：

- 架构边界、模块归属、跨模块依赖 → `docs/engineering/architecture-guardrails.md`
- 实施设计、模块接口、迁移分期、store/adapter/evidence → `docs/engineering/implementation-principles.md`
- Python CLI / engine / schema / subprocess → `docs/engineering/python-guidelines.md`
- Next.js / TypeScript / zod / API route / UI data access → `docs/engineering/frontend-guidelines.md`
- 测试计划、contract tests、flaky 控制 → `docs/engineering/testing-guidelines.md`
- ResultMatrix、Decision、Artifact/Evidence 展示 → `docs/engineering/ux-guidelines.md`
- 安全规范索引 / 不确定读哪份安全规范 → `docs/engineering/security-guidelines.md`
- 产品/服务安全：CLI、本地 UI/API、报告、发布包、未来服务化 → `docs/engineering/security-service-guidelines.md`
- 用户 run 安全：secrets、workspace、network caveat、artifact、evidence → `docs/engineering/security-user-run-guidelines.md`
- 开发实施安全：subprocess、env、redaction、workspace、artifact、decision safety → `docs/engineering/security-development-guidelines.md`
- 不确定该读哪个工程规范 → `docs/engineering/README.md`

## 开发时必须遵守安全规则

所有开发实现至少必须遵守 `docs/engineering/security-development-guidelines.md`。若改动影响用户 run 或产品服务边界，还必须读取并遵守对应安全规范。

## 维护 AGENTS.md 时

`AGENTS.md` 只放每次运行都需要的稳定行动规则。若需要改变产品、架构、schema、测试、命令或文档格式细节，先更新对应 source-of-truth 文档，再在本文件保留必要的行动路由。

## 文档维护

开发时遵守 `docs/documentation-standard.md`。尤其注意：

- 新增或移动文档目录时更新 `docs/README.md`。
- 开发过程记录写入 `docs/dev/log/`，文件名必须包含 `dev-log`。
- release gate、发布验证、质量证据写入 `docs/releases/`。
- 过时但需追溯的文档移动到 `docs/_archive/`。
- `CHANGELOG.md` 只记录面向发布/用户的版本变化。

## oh-my-codex / OMX 补充说明

本项目可以使用 oh-my-codex（OMX）作为 Codex CLI 的工作流编排层。OMX 只提供任务澄清、规划、执行编排、团队模式、状态记录和验证辅助；不得覆盖本文件中更具体的项目规则。

### OMX 工作流入口

- `$deep-interview`：需求范围、边界或意图不清楚时使用，只负责澄清，不直接实现。
- `$ralplan`：需求基本明确但需要计划、权衡或验证方案时使用。
- `$team`：任务可拆成多个独立工作流，且并行执行能明显提升质量或速度时使用。
- `$ralph`：已批准的计划需要单一负责人持续推进到完成和验证时使用。
- 常规清晰小任务默认直接执行，不为了形式而进入多代理流程。

### OMX 使用原则

- 优先直接解决问题；只有在能提升质量、速度或正确性时才委派。
- 进展更新保持简短、具体、有证据。
- 完成前必须运行与改动风险匹配的验证，并报告验证结果。
- 新用户消息优先于当前任务中的旧假设；非冲突的早前指令继续保留。
- `.omx/` 可用于保存 OMX 的状态、计划、日志和项目记忆。

### 与本项目规则的冲突处理

- 本项目明确禁止 TDD；即使 OMX 模板中出现 `$tdd`、`test first` 或类似触发词，也不得启用 TDD 工作流。
- 测试只能作为验收、回归和契约保护手段，不能作为需求来源。
- 所有代码注释仍使用英文；与用户沟通仍使用简体中文；git commit message 仍使用英文。
- 涉及 subprocess、env、stdout/stderr、artifact、workspace 写入的改动，仍必须遵守本项目 `docs/engineering/security-guidelines.md`。

### OMX Runtime Marker

保留以下 marker 供 OMX runtime/team overlay 使用；不要手动写业务规则到 marker 内部：

<!-- OMX:RUNTIME:START -->
<!-- OMX:RUNTIME:END -->

<!-- OMX:TEAM:WORKER:START -->
<!-- OMX:TEAM:WORKER:END -->
