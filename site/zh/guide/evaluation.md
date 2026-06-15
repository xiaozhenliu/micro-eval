# 评估与评分

::: tip 你在决策循环中的位置
**Evaluation** 将 Cell 的原始输出转化为分数和判断——是证据与决策之间的桥梁。
参见[设计系统](/zh/guide/design-system#three-design-tensions)了解为什么确定性检查先于 LLM 评判运行。
:::

micro-eval 使用**三层评估流水线**，将任务原始输出转化为可信、可操作的分数。每一层在上一层的基础上构建——确定性检查优先，可选的 LLM 评判其次，最后是人工标注。

```
Task output
    │
    ▼
┌─────────────────────────┐
│  Layer 1: Validator     │  Always runs — hard pass/fail, authoritative
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Layer 2: LLM Judge     │  Optional — supplemental score, no overrides
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Layer 3: Human Annot.  │  Web UI — final word, triggers recomputation
└─────────────────────────┘
```

---

## 第一层：确定性验证器

验证器会自动对结果矩阵中的每个单元格运行。它评估任务规格中定义的四种期望类型，并给出硬性的通过/失败裁定。

### 期望类型

| 类型 | 检查内容 |
|------|---------|
| `exit_code` | 进程退出状态与预期值是否匹配 |
| `contains` | stdout 或 stderr 是否包含所需字符串 |
| `file_exists` | 工作区中是否存在某文件（可选检查是否非空） |
| `command` | 后续 shell 命令是否以 0 退出（用于计算型断言） |

```yaml{6-17}
tasks:
  - id: refactor-sort
    input_payload: "Refactor the sort function in utils.py to use Timsort."
    workspace:
      type: git_repo
      path: ./fixtures/repo
      ref: main
    expectations:
      - type: exit_code
        value: 0
      - type: contains
        stream: stdout
        value: "timsort"
      - type: file_exists
        path: utils.py
      - type: command
        command: ["python", "-c", "import utils; assert utils.sort([3,1,2]) == [1,2,3]"]
        cwd: "{output_dir}"
```

### 验证器的输出

结果矩阵中每个单元格都会收到来自验证器的 `EvaluationResult`：

```json
{
  "evaluation_id": "eval_abc123",
  "cell_id": "run_01__task_refactor-sort__cfg_gpt4__rep_0",
  "evaluator_type": "deterministic",
  "evaluator": "validator_v1",
  "pass_fail": "pass",
  "score": 1.0,
  "scores": {
    "exit_code": 1.0,
    "contains": 1.0,
    "file_exists": 1.0,
    "command": 1.0
  },
  "evidence_refs": ["stdout:L1-L42", "file:utils.py"],
  "rubric_hash": "sha256:e3b0c44298fc1c149afb",
  "comment": null
}
```

::: tip evidence_refs 为必填项
只要 `pass_fail` 被设置，`evidence_refs` 就必须填充。这确保每个裁定都能追溯到具体输出——这是可审计性的设计级要求。如果证据缺失，该 run 会被标记为 `needs_human_review`。
:::

### 权威性

**确定性验证器是最终真相来源。** 验证器给出的 `fail` 裁定不能被第二层（LLM 评判）或第三层（人工标注）覆盖。这防止了评估漂移——如果代码违反了硬性契约，那它就是违反了。

`rubric_hash` 记录了评估时期望规格的 SHA-256，让你能发现两次 run 之间 rubric 本身是否发生了变化。

---

## 第二层：可选的 LLM 评判

LLM 评判**默认禁用**。当你需要评估确定性检查无法捕捉的质量——代码风格、解释质量、创意性或部分得分——时，可在 eval 配置的 `judge:` 部分启用它。

::: warning 仅作补充
LLM 评判在验证器结果之外添加分数。它**不能**将确定性的 `fail` 翻转为 `pass`。其输出标记为 `evaluator_type: llm_judge` 以避免混淆。
:::

### 配置

```yaml{1-8}
judge:
  enabled: true
  model: "claude-sonnet-4-6"
  temperature: 0.0
  threshold: 0.7
  criteria:
    - "Code is readable and follows PEP 8"
    - "Explanation is accurate and concise"
```

`judge:` 部分通过 [DeepEval](https://github.com/confident-ai/deepeval) 适配器接入。将 API 密钥设为 secret 环境变量：

```bash
export MICRO_EVAL_SECRET_ANTHROPIC_API_KEY="sk-ant-..."
# or for OpenAI:
export MICRO_EVAL_SECRET_OPENAI_API_KEY="sk-..."
```

所有 `MICRO_EVAL_SECRET_*` 变量会自动从日志、trace 和存储的 artifact 中脱敏。

### LLM 评判结果

```json
{
  "evaluation_id": "eval_def456",
  "cell_id": "run_01__task_refactor-sort__cfg_gpt4__rep_0",
  "evaluator_type": "llm_judge",
  "evaluator": "claude-sonnet-4-6",
  "pass_fail": "pass",
  "score": 0.85,
  "scores": {
    "Code is readable and follows PEP 8": 0.9,
    "Explanation is accurate and concise": 0.8
  },
  "evidence_refs": ["stdout:L1-L42"],
  "evaluator_meta": {
    "model": "claude-sonnet-4-6",
    "temperature": 0.0,
    "threshold": 0.7
  },
  "rubric_hash": "sha256:a1b2c3d4e5f6",
  "comment": "Good variable naming; explanation slightly verbose."
}
```

`evaluator_meta` 记录了评估时所用的精确模型、温度和阈值，以保证可复现性。

---

## 第三层：人工标注

人工标注是最后一层，也是**唯一能表达超出自动化系统所能捕捉的细微判断**的层次。标注通过 Web UI 的 AnnotationPanel 添加。

::: tip 启动 Web UI
```bash
micro-eval ui
# Opens http://localhost:3000
```
:::

### 添加标注

导航到结果矩阵中的任意单元格，打开 AnnotationPanel。你可以指定：

- **Score**（0.0 – 1.0）——你的数值判断
- **Comment**——自由文本说明、注意事项或后续跟进备注

标注**持久化到磁盘上的 `evaluation.json`**（位于 `.micro-eval/` 内），而非浏览器 localStorage。这意味着它们在浏览器刷新后仍然保留，由 git 追踪，并与队友共享。

```
.micro-eval/
  runs/
    run_01/
      evaluation.json   ← human annotations live here
      result_matrix.json
      trace.json
```

保存标注后，该单元格的决策会**立即重新计算**。标注的分数会按 `scoring_weights` 配置与验证器和 LLM 评判分数加权合并（默认值：`validator: 1.0`，`llm_judge: 0.5`，`human: 1.0`）。

### 标注结果

```json
{
  "evaluation_id": "eval_ghi789",
  "cell_id": "run_01__task_refactor-sort__cfg_gpt4__rep_0",
  "evaluator_type": "human",
  "evaluator": "zjulxz@hotmail.com",
  "pass_fail": "pass",
  "score": 0.9,
  "scores": {},
  "evidence_refs": ["human_review"],
  "comment": "Clean refactor. Minor: could use a docstring."
}
```

---

## EvaluationResult Schema

三层均输出相同的 `EvaluationResult` 结构，使它们可以组合使用：

| 字段 | 类型 | 描述 |
|------|------|------|
| `evaluation_id` | `str` | 本次评估事件的唯一 ID |
| `cell_id` | `str` | 关联到 `(task, configuration, repetition)` 单元格 |
| `evaluator_type` | `enum` | `deterministic` \| `llm_judge` \| `human` |
| `evaluator` | `str` | 具体的评估器名称或邮箱 |
| `pass_fail` | `enum` | `pass` \| `fail` \| `null`（尚未评估） |
| `score` | `float \| null` | 综合 0–1 分数 |
| `scores` | `dict` | 各维度得分明细 |
| `evidence_refs` | `list[str]` | 设置 `pass_fail` 时**必填** |
| `rubric_hash` | `str` | 评估时 rubric 的 SHA-256 |
| `comment` | `str \| null` | 可选自由文本备注 |
| `evaluator_meta` | `dict \| null` | LLM 评判元数据（模型、温度、阈值） |

---

## pass@k 与 pass^k 聚合

当某个 configuration 有多次重复（`repetitions: N`）时，micro-eval 使用两个互补统计量对其进行聚合。

### 定义

**pass@k** —— 至少有一次尝试通过的概率：

```
pass@k = 1 - P(all fail) = 1 - (fail_count / k)^k
```

**pass^k** —— 所有 k 次尝试都通过的概率（严格可靠性）：

```
pass^k = (pass_count / k)^k
```

### 读懂统计数据

```json
{
  "configuration_id": "cfg_gpt4",
  "task_id": "refactor-sort",
  "repetitions": 5,
  "pass_count": 4,
  "fail_count": 1,
  "pass_at_k": 0.97,
  "pass_all_k": 0.41,
  "low_sample_caveat": false
}
```

::: warning 小样本警告
当 `repetitions < 3` 时，micro-eval 会在聚合结果中附加 `"low_sample_caveat": true`。样本少于 3 时，pass@k 和 pass^k 的估计在统计上不可靠——仅将其视为方向性信号。
:::

### 如何选择

::: code-group

```yaml [Use pass@k when...]
# You care whether the agent CAN do the task at all
# (e.g., creative generation, exploratory coding)
scoring:
  aggregate: pass_at_k
  repetitions: 5
```

```yaml [Use pass^k when...]
# You care whether the agent RELIABLY does the task every time
# (e.g., CI-facing automations, critical refactors)
scoring:
  aggregate: pass_all_k
  repetitions: 5
```

:::

---

## 整体串联：评估流程

```
Run starts
  └─ for each (task × configuration × repetition):
       1. Execute agent subprocess
       2. Deterministic validator runs → EvaluationResult (deterministic)
       3. If judge.enabled: LLM judge runs → EvaluationResult (llm_judge)
       4. Results stored in evaluation.json
       5. Decision computed from all EvaluationResults
  └─ pass@k / pass^k aggregated per (task × configuration)
  └─ Web UI: human can annotate → triggers decision recompute
```

使用 `micro-eval report` 查看所有层级的分数汇总：

```bash
micro-eval report --run run_01
```

```
Run: run_01
Tasks: 3 | Configurations: 2 | Repetitions: 3

Task                Config      Validator   LLM Judge   Human   Decision
────────────────────────────────────────────────────────────────────────
refactor-sort       gpt-4o      ✓ pass      0.85        0.90    improved
refactor-sort       claude-3-5  ✓ pass      0.91        —       improved
explain-error       gpt-4o      ✗ fail      —           —       regressed
explain-error       claude-3-5  ✓ pass      0.78        —       inconclusive
add-tests           gpt-4o      ✓ pass      —           —       improved
add-tests           claude-3-5  ✓ pass      —           0.70    mixed
```

---

## 下一步

- [决策与对比](/zh/guide/decision) —— micro-eval 如何将 EvaluationResult 转化为 `improved`、`regressed`、`inconclusive` 等决策状态
