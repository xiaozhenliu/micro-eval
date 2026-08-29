# Evaluation & Scoring

::: tip Where you are in the decision loop
**Evaluation** turns raw cell output into scores and judgments — the bridge between evidence and decisions.
See [Design System](./design-system#three-design-tensions) for why deterministic checks run before LLM judgment.
:::

micro-eval uses a **three-layer evaluation pipeline** to turn raw task output into trustworthy, actionable scores. Each layer builds on the previous one — deterministic checks first, optional LLM judgment second, human annotation last.

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

## Layer 1: Deterministic Validator

The validator runs automatically on every cell in the result matrix. It evaluates the four expectation types defined in your task spec and produces a hard pass/fail verdict.

### Expectation Types

| Type | What it checks |
|------|---------------|
| `exit_code` | Process exit status matches expected value |
| `contains` | stdout or stderr contains a required string |
| `file_exists` | A file is present (and optionally non-empty) in the workspace |
| `command` | A follow-up shell command exits 0 (for computed assertions) |

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
        command: ["{python}", "-c", "import utils; assert utils.sort([3,1,2]) == [1,2,3]"]
        cwd: "{output_dir}"
```

### What the Validator Produces

Each cell in the result matrix receives an `EvaluationResult` from the validator:

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

::: tip evidence_refs is required
`evidence_refs` must be populated whenever `pass_fail` is set. This ensures every verdict can be traced back to concrete output — a design-level requirement for auditability. If evidence is missing, the run is flagged `needs_human_review`.
:::

### Authoritativeness

**The deterministic validator is the ground truth.** A `fail` verdict from the validator cannot be overridden by Layer 2 (LLM judge) or Layer 3 (human annotation). This prevents evaluation drift — if the code broke a hard contract, it broke it.

`rubric_hash` records the SHA-256 of the expectation spec at evaluation time, so you can detect if the rubric itself changed between runs.

---

## Layer 2: Optional LLM Judge

The LLM judge is **disabled by default**. Enable it in the `judge:` section of your eval config when you need to assess qualities that deterministic checks cannot capture — code style, explanation quality, creativity, or partial credit.

::: warning Supplemental only
The LLM judge adds scores alongside the validator result. It **cannot** flip a deterministic `fail` to `pass`. Its output is labeled `evaluator_type: llm_judge` to prevent confusion.
:::

### Configuration

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

The `judge:` section wires into the [DeepEval](https://github.com/confident-ai/deepeval) adapter. Set your API key as a secret environment variable:

```bash
export MICRO_EVAL_SECRET_ANTHROPIC_API_KEY="sk-ant-..."
# or for OpenAI:
export MICRO_EVAL_SECRET_OPENAI_API_KEY="sk-..."
```

All `MICRO_EVAL_SECRET_*` variables are automatically redacted from logs, traces, and stored artifacts.

### LLM Judge Result

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

`evaluator_meta` records the exact model, temperature, and threshold at evaluation time for reproducibility.

---

## Layer 3: Human Annotation

Human annotation is the final layer and the **only layer that can express nuanced judgment** beyond what automated systems capture. Annotations are added through the Web UI.

::: tip Start the Web UI
```bash
micro-eval ui
# Opens http://localhost:3000
```
:::

### Adding an Annotation

Navigate to any cell in the result matrix. You can assign:

- **Score** (0.0 – 1.0) — your numeric judgment
- **Comment** — free-text reasoning, caveats, or follow-up notes

Annotations are **persisted to `evaluation.json` on disk** (inside `.micro-eval/`), not to browser localStorage. This means they survive browser refreshes, are tracked by git, and are shared with teammates.

```
.micro-eval/
  runs/
    run_01/
      evaluation.json   ← human annotations live here
      result_matrix.json
      trace.json
```

After saving an annotation, the decision for that cell is **recomputed immediately**. The annotation's score is weighted against validator and LLM judge scores per the `scoring_weights` config (defaults: `validator: 1.0`, `llm_judge: 0.5`, `human: 1.0`).

### Annotation Result

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

## Multi-turn conversational evaluation

The three layers above evaluate a single request/response exchange. For tasks that need to assess a multi-turn conversation — does the agent stay on topic, remember earlier context, reach the intended outcome — micro-eval offers a parallel evaluation path built on DeepEval's `ConversationSimulator`. It runs instead of the Layer 2 LLM judge for tasks that opt in, and does not change the default single-turn behavior. See [Conversational evaluation](/guide/conversational-evaluation) for how to configure it, which metrics it produces, and what artifacts it writes.

---

## EvaluationResult Schema

All three layers emit the same `EvaluationResult` structure, making them composable:

| Field | Type | Description |
|-------|------|-------------|
| `evaluation_id` | `str` | Unique ID for this evaluation event |
| `cell_id` | `str` | Links to the `(task, configuration, repetition)` cell |
| `evaluator_type` | `enum` | `deterministic` \| `llm_judge` \| `human` |
| `evaluator` | `str` | Specific evaluator name or email |
| `pass_fail` | `enum` | `pass` \| `fail` \| `null` (not yet evaluated) |
| `score` | `float \| null` | Aggregate 0–1 score |
| `scores` | `dict` | Per-criterion breakdown |
| `evidence_refs` | `list[str]` | **Required** when `pass_fail` is set |
| `rubric_hash` | `str` | SHA-256 of the rubric at eval time |
| `comment` | `str \| null` | Optional free-text note |
| `evaluator_meta` | `dict \| null` | LLM judge metadata (model, temperature, threshold) |

---

## Pass@k and Pass^k Aggregation

When a configuration has multiple repetitions (`repetitions: N`), micro-eval aggregates across them using two complementary statistics.

### Definitions

**pass@k** — probability that at least one of k attempts passes:

```
pass@k = 1 - P(all fail) = 1 - (fail_count / k)^k
```

**pass^k** — probability that all k attempts pass (strict reliability):

```
pass^k = (pass_count / k)^k
```

### Reading the Stats

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

::: warning Low-sample caveat
When `repetitions < 3`, micro-eval attaches `"low_sample_caveat": true` to the aggregation. pass@k and pass^k estimates are statistically unreliable with fewer than 3 samples — treat them as directional signals only.
:::

### Choosing Between Them

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

## Putting It Together: Evaluation Flow

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

Check `micro-eval report` to see a summary of scores across all layers:

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

## Next Steps

- [Decision & Comparison](/guide/decision) — how micro-eval turns EvaluationResults into `improved`, `regressed`, `inconclusive`, and other decision statuses
