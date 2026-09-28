# Conversational Evaluation Example

Multi-turn conversational evaluation using DeepEval ConversationSimulator.

## What it demonstrates

- **JSONL subprocess bridge** — `echo_agent.py` reads/writes JSONL on stdin/stdout,
  the same protocol used by `SubprocessBridge` in the engine.
- **All 5 conversational metrics** — `conversation_completeness`, `turn_relevancy`,
  `knowledge_retention`, `role_adherence`, `goal_accuracy`.
- **Structured RubricSpec** — the `helpdesk-conversation` task uses `rubric.dimensions`
  to define evaluation axes, which maps to `ConversationalGEval`.
- **Scenario-driven simulation** — each task declares `scenario`, `expected_outcome`,
  and `user_description` fields that configure the DeepEval simulator.

## Prerequisites

```bash
# DeepEval is required for conversational metrics
pip install deepeval

# Scoring requires an LLM provider
export OPENAI_API_KEY=sk-...
```

Without these, `micro-eval validate` still works (schema validation), but
`micro-eval run` will fail on conversational tasks because the judge imports
DeepEval at runtime. Set `judge.enabled: false` in eval.yaml to run without
DeepEval (validation-only mode).

## Quick start

```bash
# From repository root
python examples/run-example.py --example conversational-eval

# Or directly
python examples/conversational-eval/run.py
python examples/conversational-eval/run.py --ui   # launch web UI after
```

## Files

| File | Purpose |
|---|---|
| `eval.yaml` | Project config with `deepeval_conversational` judge, all 5 metrics |
| `echo_agent.py` | Mock agent: reads JSONL from stdin, echoes back with a canned response |
| `tasks/conversation-task.yaml` | Basic conversation scenario (plain string rubric) |
| `tasks/helpdesk-conversation.yaml` | Helpdesk scenario with structured `RubricSpec` + dimensions |
| `run.py` | One-click runner (validate → run → report) |

## What to observe

1. **JSONL bridge protocol** — the echo agent receives `{"turn": N, "content": "..."}` on
   stdin and responds with the same format. This is the same protocol the engine's
   `SubprocessBridge` uses for real multi-turn agents.

2. **Metric scores** — in the text report and `decision.json`, look for individual metric
   scores (conversation_completeness, turn_relevancy, etc.). The echo agent is simple,
   so scores will be low — that's expected and demonstrates the scoring pipeline works.

3. **Structured rubric** — the `helpdesk-conversation` task uses `rubric.dimensions` which
   triggers `ConversationalGEval` scoring in addition to the standard metrics.
