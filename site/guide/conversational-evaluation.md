# Conversational Evaluation

micro-eval's default evaluation path scores a single prompt/response exchange. Conversational evaluation extends this to **multi-turn conversations** — it drives a simulated user through several turns with your agent and scores the conversation as a whole, using DeepEval's `ConversationSimulator`.

::: tip Parallel path, not a replacement
Conversational evaluation is opt-in per task and per configuration. It runs **instead of** the single-turn LLM judge for tasks that ask for it — the default single-turn behavior is unchanged for every other task.
:::

## What it is

Conversational evaluation replaces the Layer 2 LLM judge (see [Evaluation & Scoring](/guide/evaluation)) with a two-phase process:

1. **Simulate** — a simulated user (also LLM-driven) exchanges several turns with your agent, following a scenario you describe.
2. **Score** — once the conversation ends, a set of conversational metrics scores the transcript as a whole.

The deterministic validator (Layer 1) still runs first and remains authoritative: if it fails, conversational scoring is skipped entirely.

## When to use it

Use conversational evaluation for tasks where a single exchange cannot capture what you care about — for example, whether an agent maintains context across turns, stays on topic, or steers a conversation toward a specific outcome.

A task opts in by defining three fields (all optional, all string-typed):

| Field | Meaning |
|-------|---------|
| `scenario` | The situation the simulated user acts out across multiple turns. |
| `expected_outcome` | The outcome the conversation should reach by its end. |
| `user_description` | The simulated user's persona and goals. |

If all three are empty, the task runs through the standard single-turn path. Setting `scenario` (typically together with the other two) is what enables multi-turn simulation for that task.

## How it works

At a high level:

1. Your configured agent is launched once and stays running for the entire conversation, instead of being invoked fresh for each turn.
2. The simulated user sends a message; your agent responds; this repeats for up to `judge.max_turns` turns, or until the simulator decides the scenario has concluded.
3. Once the conversation ends, the transcript is scored against the configured metrics.
4. Results are written the same way as single-turn evaluation: an `EvaluationResult` (with `evaluator_type: conversational_judge`), evidence, and a pass/fail verdict that feeds into the cell's decision.

The same execution guarantees apply as for single-turn tasks — workspace isolation, timeouts, environment variable whitelisting, and secret redaction all carry over unchanged.

## Configuration

Set the judge provider to `deepeval_conversational` in `eval.yaml`:

```yaml
judge:
  enabled: true
  provider: deepeval_conversational
  max_turns: 5
  pass_threshold: 0.5
  conversational_metrics:
    - conversation_completeness
    - turn_relevancy
  required_secrets: []
```

Then define a task with the conversational fields:

```yaml
id: echo-conversation
name: "Echo conversation test"
description: "Test multi-turn conversation with echo agent"
input_payload: "You are a helpful assistant."
scenario: "A user asks simple questions and expects helpful responses"
expected_outcome: "The assistant responds helpfully to all questions"
user_description: "A friendly user asking basic questions"
rubric: "Evaluate whether the agent maintains a coherent, helpful conversation"
```

A full working example lives in `examples/conversational-eval/` in the repository.

::: tip Judge secrets still apply
`judge.required_secrets` works the same way as single-turn evaluation — declare any `MICRO_EVAL_SECRET_*` names the simulator or scoring metrics need, and they are injected and redacted the same way.
:::

## Metrics

`conversational_metrics` accepts any combination of the following DeepEval conversational metrics:

| Metric | What it measures |
|--------|-------------------|
| `conversation_completeness` | Whether the conversation reaches a satisfying conclusion. |
| `turn_relevancy` | Whether each agent turn is relevant to the preceding user turn. |
| `knowledge_retention` | Whether the agent retains information from earlier turns. |
| `role_adherence` | Whether the agent stays in its assigned role throughout. |
| `goal_accuracy` | Whether the conversation achieves the task's `expected_outcome`. |

If a task's `rubric` is set, micro-eval also scores the conversation with a `ConversationalGEval` metric built from that rubric text — the same rubric mechanism used by single-turn tasks.

If `conversational_metrics` is left empty, micro-eval defaults to `conversation_completeness` and `turn_relevancy`.

## Output

A conversational cell produces the same artifact and evidence shapes as any other cell, plus two additions:

- **`conversation.json`** — the full turn-by-turn transcript, written as a cell artifact alongside `stdout.txt` and `stderr.txt`.
- **`conversational_judge` evidence** — an evidence item summarizing the metric scores and pass/fail outcome, referenced from the cell's `evaluation_refs` like any other evaluation.

The cell result also records `conversation_turns` (how many turns were exchanged) and a `conversation_ref` pointing at the `conversation.json` artifact, so you can trace any decision back to the full transcript from the result matrix or the report.

## Next Steps

- [Evaluation & Scoring](/guide/evaluation) — how the three-layer pipeline works for single-turn tasks
- [task.yaml Schema](/reference/task-yaml) — full field reference including `scenario`, `expected_outcome`, `user_description`
- [eval.yaml Schema](/reference/eval-yaml) — full `JudgeConfig` reference
