# Agent Codefix Showdown

最简单的 micro-eval 入门示例。一个 Python 代码修复任务——修复账本舍入 bug——在四个本地 agent CLI 构成的矩阵中展开，使用复制式 `files` workspace、仅通过 argv 传参的包装命令，以及确定性验证。无需 LLM judge，无需外部服务。

离线冒烟路径约十秒即可完成，或在配置好本地 CLI 后切换到真实 agent。

::: tip 源码示例
本示例位于仓库的 `examples/agent-codefix-showdown/` 目录下。请先克隆仓库：
```bash
git clone https://github.com/xiaozhenliu/micro-eval.git
cd micro-eval
```
:::

---

## 你将学到什么

| 主题 | 出现位置 |
|---|---|
| `configurations[]` 矩阵 | `eval.yaml` 中的四个 configuration，每个对应一个 agent CLI |
| `files` workspace | 将 fixture 目录复制到每个 cell 独立的工作目录 |
| 仅 argv 传参的包装命令 | `run-agent.py` 和 `mock-fix-agent.py` 通过文件传递输入，而非 shell 字符串 |
| `contains` 期望 | 对结构化输出标记的确定性验证 |
| Phase 2 trace 采集 | 每个 cell 记录进程级墙钟时间 trace |
| pass@k / pass^k 聚合 | mock 路径的三次重复展示真实聚合指标 |
| `decision.json` | 每次 run 的裁定，包含 `denominator_policy`、caveats 及各 configuration 统计 |
| Web UI 复盘页 | 交互式裁定、矩阵热图与成本面板 |

---

## 前置条件

| 要求 | 说明 |
|---|---|
| Python 3.11+ | 必须 |
| 已安装 micro-eval | 在仓库根目录执行 `uv sync --all-extras`，或 `pip install micro-eval` |
| Node.js 18+ | 可选——仅在使用 Web UI（`--ui` 标志）时需要 |
| 本地 agent CLI | 可选——仅在 `--real` 模式下需要 |

::: tip 无需模型调用
默认冒烟路径使用确定性本地修复器，不调用任何 LLM。整个示例可完全离线运行。
:::

---

## 运行示例

三种模式均从**仓库根目录**通过跨平台运行器启动：

::: code-group

```bash [确定性冒烟（默认）]
# 无模型调用——验证 config、task、validation 和报告均正常工作。
python examples/run-example.py
```

```bash [真实 agent 矩阵]
# 需要已安装并登录 Claude Code、Codex CLI、OpenClaw 和 Hermes。
python examples/run-example.py --real
```

```bash [启动 Web UI]
# 启动 Next.js UI，指向本示例的 .micro-eval/ run store。
python examples/run-example.py --ui
```

:::

每次运行后，输出写入 `examples/agent-codefix-showdown/.micro-eval/runs/`，静态 `report.html` 写入示例目录。

---

## 文件结构

```text
examples/
├── run-example.py                       # 跨平台单命令运行器
└── agent-codefix-showdown/
    ├── eval.yaml                        # 真实 agent 矩阵（Claude Code、Codex CLI、OpenClaw、Hermes）
    ├── eval.mock.yaml                   # 确定性冒烟——3 次重复，开启进程 trace
    ├── tasks/
    │   └── fix-ledger-rounding.yaml     # task 定义：prompt、expectations、workspace 引用
    └── workspace/
        ├── ledger.py                    # 故意引入 bug 的 fixture
        ├── tests/
        │   └── test_ledger.py           # agent 必须使其通过的 unittest 套件
        └── scripts/
            ├── run-agent.py             # 仅 argv 传参的真实 agent 包装器（分发到四个 CLI）
            └── mock-fix-agent.py        # 冒烟路径的确定性修复器
```

每个 cell 获得 `workspace/` 的**全新副本**，写入 `.micro-eval/workspaces/{run_id}/{cell_id}/`，cell 完成后自动清理。agent 不会接触 fixture 源文件。

---

## 任务说明

该任务要求 agent 修复 `ledger.py` 中的一个函数。有 bug 的实现对每个份额取整，静默丢弃余数分：

```python
# ledger.py — 故意引入 bug
def split_amount_cents(total_cents: int, weights: list[int]) -> list[int]:
    total_weight = sum(weights)
    return [(total_cents * weight) // total_weight for weight in weights]
```

将 100 分按三个等权重分配，结果为 `[33, 33, 33]`——凭空消失了一分。

`tests/test_ledger.py` 中的测试套件描述了期望行为：

```python
def test_preserves_total_when_remainder_exists(self) -> None:
    shares = split_amount_cents(100, [1, 1, 1])
    self.assertEqual(sum(shares), 100)      # 总量必须守恒
    self.assertEqual(shares, [34, 33, 33])  # 小数部分最大的份额获得余数
```

`tasks/fix-ledger-rounding.yaml` 中的 task 定义将 prompt 与 workspace fixture 绑定，并声明验证期望：

```yaml
id: fix-ledger-rounding
name: Fix ledger rounding
workspace:
  type: files
  files:
    - workspace             # 从 examples/agent-codefix-showdown/workspace/ 复制

expectations:
  - type: contains          # 包装器在运行测试套件后写入此标记
    stream: output
    value: "MICRO_EVAL_TASK_RESULT=PASS"
  - type: contains
    stream: output
    value: "unit_test_exit_code=0"
```

两个期望均为**确定性**验证——无需 LLM。包装器在 agent 完成后在复制的 workspace 内运行 `python -m unittest`，并将结构化标记写入输出文件。

---

## Configuration 矩阵

`eval.yaml` 定义了四个 configuration——每个对应一个 agent CLI，结构相同：

```yaml{4,8-9}
configurations:
  - id: claude-code
    name: Claude Code
    role: baseline       # 第一个 config 为基准；其余为候选
    repetitions: 1
    agent:
      name: Claude Code
      command: ["{python}", "workspace/scripts/run-agent.py", "claude-code", "{output_file}"]
      input_mode: stdin   # task prompt 通过 stdin 传递
      output_mode: file   # agent 结果写入 {output_file}
      timeout_s: 900
      env: {}
      required_secrets: []

  - id: codex-cli
    name: Codex CLI
    role: candidate
    repetitions: 1
    agent:
      command: ["{python}", "workspace/scripts/run-agent.py", "codex-cli", "{output_file}"]
      # ... 结构相同
```

::: tip 仅 argv 调用
micro-eval 从不通过 shell 传递参数。`command` 列表直接通过 argv 传给 `subprocess`。占位符 `{python}` 和 `{output_file}` 由引擎在运行时替换——无 shell 插值，无注入风险。
:::

`role` 字段将某个 configuration 标记为 `baseline`，Decision 层会将每个候选与其对比。

---

## 确定性冒烟路径（eval.mock.yaml）

冒烟配置与 `eval.yaml` 结构相同，但使用单个确定性 configuration，重复三次：

```yaml{7,10}
configurations:
  - id: mock-local
    name: Local mock fixer
    role: baseline
    repetitions: 3          # 三次重复，输出真实的 pass@k / pass^k 数据
    agent:
      command: ["{python}", "workspace/scripts/mock-fix-agent.py", "{output_file}"]
      input_mode: stdin
      output_mode: file
      timeout_s: 60

trace:
  enabled: true
  provider: process         # 每个 cell 记录墙钟时间 + 退出码，无需 Langfuse
```

mock 修复器始终写入正确实现并通过测试套件。三次重复为报告层提供足够数据，展示真实的 pass@k 聚合，而不是 `low_sample` caveat。

---

## Phase 2 输出面

使用 `repetitions: 3` 和 `trace.enabled: true` 的冒烟路径演示所有 Phase 2 输出面：

### pass@k 与 pass^k 聚合

文本和 HTML 报告展示各 configuration 的聚合数据。三次全部通过时，pass@k 为 1.0，无 `low_sample` caveat：

```
Configuration: mock-local
  repetitions : 3
  pass@1      : 1.000
  pass^3      : 1.000
  decision    : inconclusive   (single config, no candidate to compare)
```

### decision.json

写入 `.micro-eval/runs/{run_id}/` 下的 `run.json` 旁：

```json
{
  "decision_report_id": "dr-20260615-001",
  "status": "inconclusive",
  "summary": "Single configuration; no candidate to compare against baseline.",
  "caveats": [],
  "per_configuration": {
    "mock-local": {
      "pass_rate": 1.0,
      "repetitions": 3,
      "denominator_policy": "include_failed"
    }
  }
}
```

### TraceRef 与成本来源

每个 cell 记录进程级 TraceRef（墙钟时间、退出码）。报告标注 mock 路径成本不可用：

```
cell: fix-ledger-rounding × mock-local × rep-1
  wall_clock_s  : 0.31
  exit_code     : 0
  cost          : n/a  (no Langfuse trace; no agent-reported cost)
```

通过设置 `trace.provider: langfuse` 并导出 `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` 可切换到 Langfuse。

### Web UI 复盘页

生成 run 后，启动 UI：

```bash
python examples/run-example.py --ui
# 或：cd ui && npm run dev
```

然后打开 `http://localhost:3000/run/{run_id}/review` 查看：

- **裁定面板** — 带活跃 caveats 的 DecisionStatus 徽标
- **矩阵热图** — 按通过率着色的 Tasks × Configurations 网格
- **Cell 详情** — 每个 cell 的 stdout、trace、成本及制品链接
- **成本面板** — 各 configuration 成本汇总（配置 Langfuse 后填充）

---

## 升级到真实 Agent

安装并认证每个本地 CLI，然后运行：

```bash
python examples/run-example.py --real
```

`--real` 标志使运行器指向 `eval.yaml` 而非 `eval.mock.yaml`。并发默认上限为 1，以避免首次使用时意外消耗大量 token 或触发 provider 限流。

每个 agent 通过 `workspace/scripts/run-agent.py` 调度，该脚本根据第一个 argv 参数选择对应的 CLI 调用方式：

```bash
# 引擎为 claude-code cell 实际执行的命令：
python workspace/scripts/run-agent.py claude-code /path/to/output_file
# stdin 携带 task prompt
```

包装器仅在 agent 运行结束后复制的 workspace 的 unittest 套件通过时，才以退出码 0 退出并向输出文件写入 `MICRO_EVAL_TASK_RESULT=PASS`。其他结果写入 `MICRO_EVAL_TASK_RESULT=FAIL`。

---

## 启用可选 LLM Judge

judge 默认禁用。在 `eval.yaml` 中启用以补充确定性验证：

```yaml{2-3}
judge:
  enabled: true
  provider: deepeval
  model: "gpt-4o"
  temperature: 0.0
  pass_threshold: 0.5
  required_secrets: [MICRO_EVAL_SECRET_OPENAI_KEY]
```

```bash
export MICRO_EVAL_SECRET_OPENAI_KEY=sk-...
```

::: warning Judge 不会覆盖确定性失败
LLM judge 分数是附加证据。一个未通过 `contains` 期望的 cell，无法因 judge 高分而被"救活"——确定性验证优先。
:::

---

## 安全注意事项

::: warning MVP 不隔离网络
本示例直接在你的机器上运行 agent CLI。agent 可能根据自身配置访问外部服务、在 workspace 副本之外写文件或消耗网络资源。MVP 不强制执行 syscall 级别的网络限制。
:::

**micro-eval 提供的保护：**

- 每个 cell 在一次性临时目录中获得 `workspace/` 的**全新副本**。fixture 源文件不会被修改。
- agent 子进程获得**最小化环境**——仅包含 `PATH`、`HOME`、临时目录变量和 `NO_COLOR`。宿主环境中的凭证不会透传。
- `required_secrets` 中声明的 **`MICRO_EVAL_SECRET_*` 变量**在运行时注入，并从所有日志、trace 和存储制品中**自动脱敏**。
- 输出大小上限为 `output_cap_bytes`，制品大小上限为 `artifact_cap_bytes`，防止无限写入。

**你需要自行处理的事项：**

- 运行真实 agent 时，不要将高权限凭证（云服务商密钥、生产 token）放入环境变量。
- 不要在 task prompt 中放置敏感数据——某些 CLI 包装器为兼容本地 CLI 会将 prompt 文本作为 argv 传递。
- 分享报告前，请检查 `.micro-eval/runs/` 下的制品。
- 如果 agent 需要密钥，请使用 `MICRO_EVAL_SECRET_` 通道——切勿将值硬编码在 YAML、prompt 或 fixture 文件中。

如需更强隔离，请参阅 [Git Workspace Isolation](/zh/examples/git-workspace-isolation)，该示例演示 OS 策略沙箱（macOS 上的 Seatbelt、Linux 上的 Bubblewrap）以及通过 E2B/Modal 的远程 VM 执行。

---

## 下一步

- **[Multi-Task Matrix](/zh/examples/multi-task-matrix)** — 扩展到包含四种期望类型和 setup 命令的 2 × 3 × 2 cell 矩阵
- **[Git Workspace Isolation](/zh/examples/git-workspace-isolation)** — Phase 3 沙箱、fixture digest、toolchain fingerprint 与趋势分析
- **[Tasks 参考](/zh/guide/tasks)** — 完整 task schema，包含所有期望类型和 rubric 字段
- **[Configuration 参考](/zh/guide/configuration)** — 完整 `eval.yaml` 字段文档
