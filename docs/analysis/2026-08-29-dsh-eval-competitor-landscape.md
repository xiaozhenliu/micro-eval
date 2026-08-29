---
title: DSH 评测生态竞品调研（以 dsh-eval-harness 为重点）
doc_type: analysis
status: active
created_at: 2026-08-29T17:59+08:00
updated_at: 2026-08-29T17:59+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - competitor
  - deepseek-harness
  - ecosystem
  - evaluation
  - distribution
related:
  - docs/analysis/2026-08-24-deepseek-harness-integration.md
  - docs/analysis/2026-08-26-benchmark-compatibility-evaluation.md
  - .plan/user-activation-and-dsh-growth-intent.md
  - src/micro_eval/decision/aggregation.py
  - micro-eval-brd.md
---

# DSH 评测生态竞品调研（以 dsh-eval-harness 为重点）

## 文档定位

本文记录 2026-08-29 对 DeepSeek Harness（DSH）插件评测生态的一次外部调研，重点分析
与 micro-eval 定位最接近的公开项目 `BiBoyang/dsh-eval-harness`。

本文用于保留可复核的事实基础，**不是产品规格、路线图承诺或竞争策略决策**。它不主张
micro-eval 应当或不应当进入 DSH 生态；那属于 `.plan/user-activation-and-dsh-growth-intent.md`
的范围，且需另行建立 ticket。

它与 [`2026-08-24-deepseek-harness-integration.md`](2026-08-24-deepseek-harness-integration.md)
互补：那份文档回答"micro-eval 技术上如何接入 DSH"，本文回答"DSH 评测这个位置上已经有谁、
做到了什么程度"。

**证据强度说明**：竞品能力分析基于其公开 README 与 npm/GitHub 元数据，**未阅读其源码**，
未实际安装运行。凡本文描述其行为之处，均为其文档自述，不构成独立验证。

## 1. 调研方法

全部数据于 2026-08-29 采集，可用以下命令复核：

```bash
gh api repos/deepseek-ai/deepseek-harness --jq '{stars:.stargazers_count,forks:.forks_count}'
gh api "search/repositories?q=topic:dsh-plugin&per_page=1" --jq '.total_count'
gh api "search/repositories?q=dsh+eval+in:name,description&sort=stars&per_page=5"
gh api repos/BiBoyang/dsh-eval-harness --jq '{stars:.stargazers_count,pushed:.pushed_at}'
curl -s "https://api.npmjs.org/downloads/range/last-month/dsh-eval-harness"
```

GitHub 星数在 16 天龄的生态中主要反映发布波与仓库类型，不能作为需求或使用量的度量。
本文因此把星数与实际下载量分开呈现，并优先采信后者。

## 2. DSH 生态规模

| 项 | 值 |
| --- | --- |
| `deepseek-ai/deepseek-harness` stars / forks | 202,653 / 23,322 |
| 创建时间 | 2026-08-13（调研时 16 天） |
| 最新 release | `dsh-v0.1.2-alpha.1`（2026-08-27），14 天内 5 个 release |
| 语言 / license | TypeScript / MIT |
| Issues | 关闭；只开放 Discussions |
| topic `dsh-plugin` 仓库数 | 12,520 |
| topic `dsh` 仓库数 | 5,645 |

对 micro-eval 有直接意义的两点：DSH 主仓库关闭了 Issues，任何社区接触只能经由
Discussions；release 频率为每 2–3 天一次且仍在 alpha，任何 adapter 的兼容维护成本
按周计算，而非按月。

## 3. 竞品格局

搜索命中数：`dsh+eval` 36 个仓库，`dsh+benchmark` 33 个，`dsh+plugin+test` 55 个。
评测类项目全部低于 15 stars。

同期生态内关注度分布：

| 仓库 | stars | forks | 类别 |
| --- | --- | --- | --- |
| `awesome-dsh-plugin` | 13,473 | 2,299 | 发现（精选列表） |
| `dsh-market` | 2,729 | 146 | 发现（可视化市场，一键安装） |
| `dsh-suite` | 49 | 10 | 发现（目录，每小时刷新 + 每日兼容性测试） |
| `BiBoyang/dsh-eval-harness` | 12 | 1 | 评测（回归门禁） |

**这组数字不能推导需求。** 精选列表的 star 成本为零且具社交信号价值，评测工具需要安装
和配置才能产生第一个结果；两者的 star 语义不可比。第 5 节给出的下载量数据说明星数在
这里显著低估了实际使用。

可以成立的结论只有两条：评测这个位置在 16 天内已被至少 36 个团队独立识别；截至调研时
无人取得明显领先。

## 4. dsh-eval-harness 深度分析

### 4.1 基本情况

| 项 | 值 |
| --- | --- |
| 仓库 | `BiBoyang/dsh-eval-harness` |
| 创建 | 2026-08-13T22:13Z（DSH 发布当日） |
| 最近 push | 2026-08-26 |
| stars / forks / watchers | 12 / 1 / 1 |
| 提交 / 贡献者 | 33 / 1（单人项目） |
| 语言 / 体积 | TypeScript / 437 KB |
| license | GitHub 无 license 文件；npm 元数据标 MIT（不一致，引用其代码前需澄清） |
| npm 包 | `dsh-eval-harness`，最新 `0.3.1`，首发 2026-08-14 |

### 4.2 分发方式

这是它与 micro-eval 最本质的差别：**它本身就是一个 DSH 插件**。

```sh
dsh plugin --profile headless add dsh-eval-harness
```

安装后向 DSH 暴露三个 tool（`eval_run`、`eval_gate`、`eval_judge_validate`）和一个
skill（`eval`，教模型帮用户写评测用例）。用户不离开 DSH，不安装第二个运行时。

micro-eval 是独立 Python CLI，需要 uv/Python 环境、独立 YAML、独立报告入口，且当前
**未发布到 PyPI**（`https://pypi.org/pypi/micro-eval/json` 返回无此项目）。

### 4.3 执行模型

逐条用例 fork `dsh --profile headless --patch <overlay> <prompt>` 子进程，用 overlay
把会话落盘切到隔离目录，每条用例独立 workspace，支持 `concurrency` 并行。

这与 [`2026-08-24-deepseek-harness-integration.md`](2026-08-24-deepseek-harness-integration.md)
中"候选 A：headless wrapper"的判断一致——headless profile 确实是接入 DSH 成本最低的
路径，并且已被一个真实项目验证可行。该文档推荐的路径得到了外部佐证。

值得注意：其 README 全程使用 headless CLI 与 session trace 文件，**未出现 Python SDK**。
`.plan` §5.2 以 DSH Python SDK 作为集成依据，该依据尚未在本文调研范围内得到确认。

### 4.4 断言体系

它解析 DSH 落盘的 `session.jsonl` / `session.jsonl.zstd` trace 做断言，因此断言对象是
**agent 的内部执行轨迹**，而不仅是最终产物：

| 断言 | 作用 |
| --- | --- |
| `turn_end` | turn/end 事件的 reason.kind |
| `tools_called` | 工具调用名称的保序子序列 |
| `tools_exact` | 工具调用序列完全一致 |
| `tools_not_called` | 指定工具一次都不能被调用 |
| `max_steps` / `max_tokens` | 步数与 token 预算上限 |
| `no_tool_errors` | 任何工具硬错误即 fail |
| `tool_args_contains` / `tool_result_contains` | 工具入参与结果的内容断言 |
| `output_contains` / `output_not_contains` / `output_matches` | 最终文本包含、不含、正则 |
| `output_judge` | LLM rubric 语义评审 |

micro-eval 当前的 expectation 只有 `exit_code`、`contains`、`file_exists` 和 argv-only
`command` 四种，全部作用于最终产物或 workspace 状态。**trace 级断言是 micro-eval 完全
没有的一整类能力。**

其 README 给出的一个具体价值案例：`no_tool_errors` 用于拦截"工具报错但 agent 兜底答对"
的假通过——这类失败在只看最终输出的断言体系里不可见。

### 4.5 可靠性测量

`trials > 1` 时用例跑满 n 次隔离 attempt（每次前清空 workspace、不重试），报告写入
per-case `reliability`：`successRate`、`passAtK`、`passPowK`。

其 README 明确说明估计量选择：

- `passAtK` = 1 − C(n−c,k)/C(n,k)
- `passPowK` = C(c,k)/C(n,k)，并明确**不使用 plug-in 的 (c/n)^k**，理由是 x^k 上凸，
  Jensen 不等式保证该估计向上偏。

它还区分 `retries`（失败重跑，用于容错）与 `trials`（独立试次，用于测量），并规定
`trials > 1` 时忽略 retries——测量必须是无重试干预的原始单次成功率。这个区分在
micro-eval 中不存在。

### 4.6 门禁协议

`eval_gate` 对比 baseline 与本次报告，输出 `OVERALL=PASS|WARN|FAIL|N/A` 与 CI 退出码：

| 条件 | 判定 | 退出码 |
| --- | --- | --- |
| PASS → FAIL/error，或新增用例即 FAIL/error | `FAIL` | 1 |
| FAIL/error → PASS，或用例数量变化 | `WARN` | 0（strict 为 2） |
| 状态不变但 token 涨幅超阈值（默认 +50%） | `WARN` | 0（strict 为 2） |
| trace 解析漏帧较 baseline 增多 | `WARN` | 0（strict 为 2） |
| 新增 flaky 用例（重跑后才过） | `WARN` | 0（strict 为 2） |
| pass 但带工具硬错误的用例新增 | `WARN` | 0（strict 为 2） |
| 同一 stderr 错误签名跨用例出现 ≥2 次 | `WARN` | 0（strict 为 2） |
| trials successRate 的单侧 95% Wilson 下界低于阈值 | `WARN` | 0（strict 为 2） |
| dsh 版本较 baseline 变化 | 仅 informational，不影响判定 | - |
| 全部一致 | `PASS` | 0 |
| 无 baseline | `N/A` | 2 |

报告写 `schemaVersion: 1`，`eval_gate` 严格校验，旧 baseline 按 legacy schema 0 兼容读取；
报告头部记录 `dshVersion` 探针，用于区分"dsh 变了"与"模型变了"。

这套判定的软信号设计（flaky、漏帧、共享态事故签名、token 膨胀）覆盖的是可比性风险，
与 micro-eval 的 caveat 与 snapshot gate 属于同一问题域，实现方式不同。

### 4.7 LLM judge 校准

`eval_judge_validate` 在人工标注 JSONL 上跑 judge，报混淆矩阵与 TPR/TNR，两个指标
都 ≥ 阈值（默认 0.9）才算 `calibrated`。其 README 明确指出只看 agreement 会被不平衡
标注集欺骗——标注集 90% 为 pass 时，全部放行的 judge 也能拿到 90% agreement。

它同时规定了 judge 的使用纪律：结构断言优先、judge 只兜语义；结构断言全过后才调 judge；
judge 调用失败按 `error` 而非 `fail` 处理（基础设施抖动不是断言失败）；换 judge 模型、
升级 harness prompt 或被测输出分布变化时必须重新校准。

micro-eval 的 judge 为 default-off 的补充评估，不覆盖 deterministic 结果，但**没有校准
机制**。

## 5. 关注度与使用量的关系

`dsh-eval-harness` 的 npm 下载量（last-month，2026-08-29 采集）：

- 合计 **613** 次
- 日基线约 30–45 次，2026-08-24 出现单日 179 的尖峰

同期 GitHub stars 为 12。**下载与 star 的比值约 50 : 1。**

两条结论：

1. 在这个生态里，star 数严重低估实际使用。第 3 节的星数分布不能用来判断需求存在与否。
2. 613 次/月是小量级但非零，且有稳定日基线。npm 下载量包含 CI、镜像与爬虫流量，
   不能等同于真实用户数，因此只能作为"存在某种持续使用"的下界证据。

micro-eval 当前无 PyPI 发布，没有可对照的分发量数据。

## 6. 能力对照

| 维度 | micro-eval | dsh-eval-harness |
| --- | --- | --- |
| 被评测对象 | 任意 argv 命令，agent 无关 | 仅 DSH |
| 分发 | 源码 checkout；未发布 PyPI | DSH 插件 + npm 包 |
| 执行单元 | Tasks × Configurations × Repetitions 矩阵，N 个 configuration | cases × trials，baseline 对比为时间维度的两点 |
| 断言对象 | 最终产物与 workspace 状态（4 种 expectation） | agent 执行 trace（13 类断言） |
| 起点控制 | SameStartSnapshot、fixture digest、toolchain fingerprint、git worktree、OS 沙箱、远程 provider | 隔离 session 根 + 独立 workspace；记录 dsh 版本 |
| 比较结论 | 枚举已定义但当前不可达（见 LOCAL-COMPARATIVE-DECISION-01） | PASS/WARN/FAIL + CI 退出码，已可用 |
| pass@k | 无偏估计 | 无偏估计 |
| pass^k | plug-in `(c/n)^k`，向上偏（见第 7 节） | 无偏估计 `C(c,k)/C(n,k)` |
| 重试与试次 | 未区分 | `retries` 与 `trials` 分离，trials 禁用重试 |
| judge | default-off 补充评估，无校准机制 | rubric judge + TPR/TNR 校准工具与使用纪律 |
| 证据链 | ArtifactRef / EvidenceItem / TraceRef + manifest；人工评估持久化；UI | report.json / report.md + attemptResults；无 UI |
| 跨 run 趋势 | SQLite 索引 + drift breakpoint | 无（只有 baseline 两点对比） |
| 团队协作 | Team Server（workspace 隔离、串行队列、模板库） | 无 |

micro-eval 的相对优势集中在 agent 无关性、起点可复现性、证据链完整性与跨 run 趋势；
dsh-eval-harness 的相对优势集中在分发路径、trace 级断言、可用的门禁结论与统计严谨性。

## 7. 由本次调研发现的 micro-eval 缺陷

竞品 README 明确点名的 plug-in 估计量偏差问题，在 micro-eval 中存在。

`src/micro_eval/decision/aggregation.py`：

- `_pass_at_k(n, c)` 使用 `1.0 - comb(n - c, k) / comb(n, k)`，为无偏估计，正确。
- `_pass_hat_k(n, pass_rate)` 使用 `pass_rate ** k`，为 plug-in 估计量。

数值验证，取 `examples/multi-task-matrix` 现有 artifact 中 checker-beta 的 n=6、c=4：

| 量 | micro-eval 输出 | 无偏估计 |
| --- | --- | --- |
| pass@2 | 0.9333 | 1 − C(2,2)/C(6,2) = 0.9333 ✅ |
| pass^2 | 0.4444（= (4/6)²） | C(4,2)/C(6,2) = 6/15 = 0.4 |
| pass^3 | 0.2963（= (4/6)³） | C(4,3)/C(6,3) = 4/20 = 0.2 |

`pass^k` 被系统性高估，且 k 越大偏差越大（k=3 时 0.296 对 0.2，高估约 48%）。
`pass^k` 的语义是"连续 k 次全部通过的概率"，高估会让稳定性看起来比实际好，方向上
不利于 micro-eval 的保守决策立场。

**本条为独立复核发现，需另立 ticket 处理，不在本文范围内决定修法。**

## 8. 未验证事项与开放问题

1. 未阅读 `dsh-eval-harness` 源码，其 README 自述的行为未经独立验证。
2. 其 license 状态不一致（GitHub 无 license 文件 / npm 标 MIT），引用其设计以外的
   任何内容前需澄清。
3. npm 下载量的构成（真实用户 / CI / 镜像 / 爬虫）不可分解，只能作为下界。
4. 未调研其余 35 个 `dsh+eval` 仓库，不排除存在更成熟但未被搜索命中的项目。
5. DSH 是否存在一等公民的 Python SDK 未确认；这直接影响 `.plan` §5.2 的集成依据。
6. 未采集需求侧证据（DSH Discussions 中用户是否主动提出插件效果验证需求）。
7. 未确认发现层项目（`dsh-market`、`awesome-dsh-plugin`、`dsh-suite`）是否已引入质量
   或评测维度，以及是否接受外部证据供给。

## 9. 对后续判断的输入

以下为本文可支撑的事实性输入，不构成路线图建议：

- DSH 作为获取渠道的规模不需要再验证；12,520 个插件仓库使"选哪个插件"成为真实且高频
  的问题。
- 评测这个位置已有 36 个项目在做，无人领先；进入不受先发优势阻碍，但也不存在空白区。
- headless profile 作为接入路径已被外部项目实证可行，与本仓库 8-24 分析文档的候选 A
  判断一致。
- 分发方式是竞品的主要优势来源。micro-eval 未发布 PyPI，其首次安装成本高于一条
  `dsh plugin add`。
- 竞品已具备可用的比较门禁，micro-eval 的同类能力仍在 LOCAL-COMPARATIVE-DECISION-01 中规格化。这不是
  功能数量差距，而是核心承诺兑现顺序的差距。

## 10. 参考资料

- [dsh-eval-harness 仓库](https://github.com/BiBoyang/dsh-eval-harness)
- [dsh-eval-harness npm 包](https://www.npmjs.com/package/dsh-eval-harness)
- [DeepSeek Harness 仓库](https://github.com/deepseek-ai/deepseek-harness)
- [awesome-dsh-plugin](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin)
- [dsh-market](https://github.com/dsh-market/dsh-market)
- [dsh-suite](https://github.com/whyihaveyou/dsh-suite)
- [DSH 接入可行性研究](2026-08-24-deepseek-harness-integration.md)
- [Benchmark 兼容性评估](2026-08-26-benchmark-compatibility-evaluation.md)
