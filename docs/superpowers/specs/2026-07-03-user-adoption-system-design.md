# 用户采纳体系设计（User Adoption System Design）

- 日期：2026-07-03
- 状态：**方案草案，未开始实施**。三个决策点待拍板（见 §8）。
- 范围：用户定义、免费/付费边界、采纳漏斗、个人 vs 团队入口分流、反馈回路。
- 性质：本文档是后续所有降摩擦改动的"裁判文档"——任何 onboarding / 文档 / 分发相关改动应先对照本文档判断归属与优先级。

---

## 1. 问题陈述

项目已经积累了多种降摩擦资产（文档站、examples、README、旅程测试），但存在三个上游定义缺失，导致这些资产是并列堆放而非系统：

1. **用户定义不可操作**——BRD 只有"1–20 人 AI 小团队中的 agent 开发者"这一个市场定位，没有拆出角色，个人用法和团队用法界定不清。
2. **免费/付费边界未定义**——项目定位为"开源 + 未来商业化升级"，但没有裁判规则判断哪些功能永久免费、哪些留作付费。
3. **资产与旅程未对齐**——每个资产（README、init、examples、文档站、Team Server 文档）没有被指派到用户旅程的具体一步，也没有对应指标。

## 2. 现状事实清单（2026-07-03 核实）

| 资产 | 现状 | 主要问题 |
|---|---|---|
| README（中英双语） | ~310 行，含 Why/Features/Quick Start/CLI 表/配置/安全/架构等 | 是手册不是落地页；无个人/团队分流 |
| 文档站（VitePress，GitHub Pages 已部署） | 中英双语 44 页；sidebar 旅程式分组（入门/使用/进阶/参考）；有 Design System 页 | Team Server 只是"进阶"里一页，无 P2/P3 分角色入口 |
| examples/ | 4 个（codefix-showdown、multi-task-matrix、git-workspace-isolation、conversational-eval），有能力覆盖矩阵 | 无编号/学习顺序标注；conversational-eval 缺 README 且不在索引表和 site examples 页中 |
| `micro-eval init` | 一步式 scaffold：eval.yaml + tasks/hello.yaml + 2 个 template task | starter 的 baseline/candidate 都是 `["cat"]`，跑通但看不出差异（aha 时刻缺席）；run 完不提示下一步 |
| 分发 | 未发 PyPI，仅 git clone + `uv sync --all-extras`（+ UI 需 `npm install`） | 最大单点摩擦 |
| Team Server（v0.4） | 已免费开源；成员旅程实测有 15 项问题，其中 6 项 A 类阻断（`docs/analysis/2026-07-02-team-server-member-journey-gaps.md`，bug 清单在 `docs/bug_reports/2026-07-02-1630-team-server-member-journey-findings.md`） | 成员无法纯浏览器完成首次评测 |
| 反馈渠道 | 无 issue 模板、无 Discussions、无 CONTRIBUTING.md、无遥测 | 用户想反馈没有槽位 |

## 3. 业界参照系

开源 + 商业化升级的小团队项目（PostHog、Supabase、Cal.com、Plausible 早期）的通行模式：

- **个人用户负责传播，团队场景负责变现**：个人开发者自己装、自己用、觉得好，再带进团队；商业化发生在团队想要"更省心/更合规"的那一刻。
- **GitLab 的 buyer-based 判据**：一个功能是"个人开发者自己要用的"→ 免费开源；是"经理/公司才会掏钱买的"（SSO、权限、审计、托管）→ 留作付费。判断标准是**谁掏钱**，不是功能强弱。
- **漏斗每层只有一个任务、一个指标**，资产为漏斗服务。

注：BRD §9.2（Team 版、Hosted reports、付费 judge）已经天然符合 buyer-based 判据；CLAUDE.md「MVP 不做 RBAC/SSO/审计」恰好把未来付费功能空间完整留出。

## 4. 用户定义：三个 persona

| 角色 | 是谁 | 用什么 | 成功标准（验收口径） |
|---|---|---|---|
| **P1 个人开发者** | 独立开发者 / 团队里先自己试的人 | `micro-eval` CLI + 本地 `ui` | 10 分钟内看到第一个矩阵对比结论（沿用现有标准） |
| **P2 团队搭建者** | P1 用爽后在团队推广的人（champion） | `micro-eval serve` + 模板库 | 半天内搭好 server、备好模板，能把地址甩给同事 |
| **P3 团队成员** | 只用浏览器的消费者，不装任何东西 | Web UI（server 模式） | 拿到地址 + 一句话说明，10 分钟不问人跑完第一次评测并读懂结论（采纳自旅程测试文档的验收基准） |

**关键认知：P2 不是新用户，是升级后的 P1。** 个人路径是团队采纳的唯一入口——个人体验做不好，团队场景没有机会发生。因此激活层（P1 首跑体验）的优先级永远高于扩散层。

## 5. 免费/付费边界

### 备选方案

- **方案 A（推荐）**：单机全功能 + 可信内网 Team Server **永久免费开源**；未来付费候选 = 托管版（hosted）、SSO/RBAC/审计、跨团队报告、托管 LLM judge。
  - 理由：符合 buyer-based 判据；不收回任何已发布功能（收回已开源功能是社区大忌）；与 BRD §9.2 一致，只需正式化。
- **方案 B**：全部免费，商业化推迟到有真实用户量之后再定。
  - 风险：之后每个新功能都要临时争论"该不该免费"，决策成本反而更高。

### 推荐落法（A 的轻量版）

用本节把边界原则**写死但不实现任何收费**：

1. **判据（一句话）**：个人开发者独自使用所需的一切功能，永久免费开源；只有组织/管理者才会付费购买的能力（托管、身份与权限、合规审计、跨团队聚合），保留为未来商业层。
2. **已知付费候选清单**：Hosted 版本、SSO/RBAC、审计日志、跨团队报告聚合、托管/计费型 LLM judge。
3. **已明确永久免费**：本地 CLI 全功能、本地 Web UI、可信内网 Team Server（v0.4 已发布形态）、全部评分与趋势分析能力。

> 决策点 1：是否接受方案 A。见 §10。

## 6. 采纳漏斗：五层定义

每层一个用户任务、一个负责资产、一个可测指标（全部不依赖埋点）：

| 漏斗层 | 用户在干嘛 | 负责资产 | 指标 | 现状缺口 |
|---|---|---|---|---|
| **发现** | 30 秒判断"跟我有关吗" | README 首屏 + 文档站落地页 | GitHub star/clone/traffic、站点访问 | README 过重，无分流 |
| **激活** | 第一次跑通、看到结论（aha 时刻） | `init` + 快速开始 + 第一个 example | 10 分钟标准的真人实测通过率 | 未发 PyPI；starter 无差异无结论；run 完无下一步提示 |
| **留存** | 换上自己的 agent/task 真用起来 | examples 学习路径 + 使用指南 | 访谈问"第二次用是什么时候" | examples 无编号顺序；conversational-eval 缺 README 与索引 |
| **团队扩散** | P1 变成 P2，拉同事进来 | Team Server 文档 + P3 浏览器旅程 | 一个团队里的活跃成员数 | 6 项 A 类旅程阻断；无 P2/P3 分角色文档 |
| **商业转化**（未来） | 团队想要托管/合规 | §5 边界文档 | 暂不度量 | 暂不做，只留定义 |

### aha 时刻的严格定义

不是 `micro-eval run` 退出码为 0，而是**用户看着矩阵说出"哦，candidate 在这个 task 上确实更强"**。当前 `init` 生成的 starter 用 `cat` 当 agent 且 baseline/candidate 配置相同——跑通了但看不出差异，aha 时刻缺席。激活层最高杠杆改动：starter 内置一对**有可见差异**的 mock 配置，让第一次 run 就产出一个有结论的矩阵。

## 7. 个人 vs 团队：入口分流设计

当前问题：README 和 getting-started 把 Team Server 当"最后一节的可选功能"，个人/团队界定不清的直接原因。

改法（均为方案，未实施）：

1. **README / 文档站落地页第一屏三分流**：
   - "一个人用" → 本地模式快速开始（5 分钟）
   - "给团队搭" → Server 搭建指南（半天）
   - "同事发给你一个地址" → 成员使用指南（10 分钟，纯浏览器）
2. **文档站 sidebar 保持现有旅程式分组**，但"团队服务器"拆为两页：《搭建 Team Server》（P2）与《作为成员使用》（P3）。**P3 页面不允许出现任何 CLI 命令。**
3. **模式定义一句话化并提升到用户文档层**（本地 vs server 对比表已存在于 `docs/superpowers/specs/2026-06-19-team-server-design.md`，提升到用户文档即可）：
   - 本地模式 = 数据在项目 `.micro-eval/`、单人、直接执行。
   - Server 模式 = 数据在 server、多人、串行队列执行。

## 8. 反馈回路：轻量、无遥测

- **不做产品内遥测**（建议写入项目原则）。local-first + 开发者人群 + 评测内容涉及用户自己的 agent 与代码，遥测的信任损失大于数据收益。
- 三个替代信号：
  1. GitHub Insights（star/clone/traffic）；
  2. 文档站访问统计（可选，隐私友好方案如 GoatCounter/Plausible，待决策点 3）；
  3. **人工访谈**——BRD §3.2 的"找 5–10 个 agent 开发者验证"即现阶段最好的漏斗测量：让真人照 getting-started 跑，旁观计时并记录卡点。
- 补齐最低配社区设施：GitHub issue 模板（bug / 体验卡点两种）+ 开启 Discussions + CONTRIBUTING.md。

## 9. 落地顺序（三阶段，均未开始）

1. **阶段 A：定义层（纸面，约 1 天）**——本文档定稿即完成大半；产出 persona、边界原则、漏斗定义作为裁判文档。
2. **阶段 B：激活层（最高杠杆工程活）**：
   - 发布 PyPI 包（分发策略见决策点 2）；
   - `init` starter 改为"有差异、有结论"的一对 mock 配置，run 完输出下一步提示；
   - README 瘦身为落地页 + 三分流，深度内容移文档站；
   - examples 编号排序（01/02/03/04），补 conversational-eval 的 README 与索引。
3. **阶段 C：扩散与反馈层**：
   - 修复 P3 旅程 6 项 A 类阻断（bug 清单已有）；
   - 文档站 P2/P3 分页与三分流落地；
   - issue 模板 + Discussions + CONTRIBUTING.md；
   - 按 BRD §3.2 执行 5–10 人真人计时测试，用结果回修阶段 B。

## 10. 待拍板决策点

| # | 决策 | 选项 | 倾向 |
|---|---|---|---|
| 1 | 免费/付费边界 | A：内网 Team Server 永久免费，托管/SSO/审计留作付费 ／ B：全免费暂不定边界 | A（轻量版，只写原则不实现收费） |
| 2 | PyPI 发布策略 | 先发 CLI-only 包（ui/serve 提示需额外安装） ／ 等 UI 打包方案一起发 | 先发 CLI-only，立刻消掉最大摩擦 |
| 3 | 文档站统计 | 完全不加 ／ 加隐私友好统计（GoatCounter/Plausible） | 待定，两者皆可接受 |

## 11. 与权威来源的关系

- 本文档不改动任何 schema 字段、模块契约或 MVP 范围（遵守 CLAUDE.md 工程规范约束）。
- persona 定义是对 BRD §3.1/§3.3 的细化，不与其冲突；若 BRD 后续修订用户定义，以 BRD 为准并回改本文档。
- P3 成功标准直接采纳 `docs/analysis/2026-07-02-team-server-member-journey-gaps.md` 的验收基准。
