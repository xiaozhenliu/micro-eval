# 会话评测

micro-eval 默认的评测路径为单次 prompt/response 交互打分。会话评测在此基础上扩展出**多轮会话**评测能力——它借助 DeepEval 的 `ConversationSimulator`，驱动一个模拟用户与你的 agent 进行多轮对话，并对整段会话打分。

::: tip 并行路径，而非替代
会话评测按 task、按 configuration 选择性启用。对于选择启用它的 task，它会**取代**单轮 LLM judge 运行——其余所有 task 的默认单轮行为不受影响。
:::

## 是什么

会话评测取代 Layer 2 的 LLM judge（参见[评估与打分](/zh/guide/evaluation)），分两个阶段进行：

1. **模拟（Simulate）** — 一个同样由 LLM 驱动的模拟用户，按照你描述的场景，与你的 agent 进行多轮交互。
2. **打分（Score）** — 会话结束后，一组会话类 metric 对整段对话记录进行打分。

确定性验证器（Layer 1）仍然最先运行且保持权威性：如果它判定失败，会话打分会被完全跳过。

## 何时使用

当单次交互无法反映你真正关心的东西时，使用会话评测——例如 agent 是否能在多轮之间保持上下文、是否跑题、是否能把对话引导到特定结果。

一个 task 通过定义三个字段（均为可选，均为字符串类型）来选择启用会话评测：

| 字段 | 含义 |
|------|------|
| `scenario` | 模拟用户在多轮对话中扮演的场景。 |
| `expected_outcome` | 该对话到结束时应达成的结果。 |
| `user_description` | 模拟用户的人设与目标。 |

三者全部为空时，该 task 走标准单轮路径。设置 `scenario`（通常连同另外两个字段一起）即可为该 task 启用多轮模拟。

## 工作原理

概括来说：

1. 配置的 agent 只启动一次，并在整段会话期间保持运行，而不是每一轮都重新调用一次。
2. 模拟用户发送一条消息，agent 作出回应，如此往复，最多进行 `judge.max_turns` 轮，或直到模拟器判定场景已经结束。
3. 会话结束后，整段对话记录会按照配置的 metric 进行打分。
4. 结果的写入方式与单轮评测一致：一条 `EvaluationResult`（`evaluator_type: conversational_judge`）、对应的 evidence，以及一个汇入该 cell decision 的 pass/fail 判定。

单轮任务的各项执行保障在这里同样适用——workspace 隔离、超时、环境变量白名单、secrets 脱敏均保持不变。

## 配置

在 `eval.yaml` 中将 judge provider 设为 `deepeval_conversational`：

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

然后定义带有会话字段的 task：

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

仓库中的 `examples/conversational-eval/` 提供了一份可直接运行的完整示例。

::: tip judge secrets 同样适用
`judge.required_secrets` 的用法与单轮评测完全一致——声明模拟器或打分 metric 所需的 `MICRO_EVAL_SECRET_*` 名称，它们会以相同方式被注入和脱敏。
:::

## Metrics

`conversational_metrics` 可以任意组合以下 DeepEval 会话类 metric：

| Metric | 衡量的内容 |
|--------|-----------|
| `conversation_completeness` | 会话是否达成了令人满意的结论。 |
| `turn_relevancy` | agent 每一轮回复是否切合上一轮用户输入。 |
| `knowledge_retention` | agent 是否记住了前面轮次中的信息。 |
| `role_adherence` | agent 在整个会话中是否保持既定角色。 |
| `goal_accuracy` | 会话是否达成了 task 的 `expected_outcome`。 |

如果 task 设置了 `rubric`，micro-eval 还会用基于该 rubric 文本构建的 `ConversationalGEval` metric 对会话打分——与单轮 task 使用的是同一套 rubric 机制。

如果 `conversational_metrics` 留空，micro-eval 默认使用 `conversation_completeness` 和 `turn_relevancy`。

## 产物

一次会话评测 cell 产出的 artifact 与 evidence 形态和其他 cell 一致，另外增加两项：

- **`conversation.json`** — 完整的逐轮对话记录，作为该 cell 的一个 artifact，与 `stdout.txt`、`stderr.txt` 一起写入。
- **`conversational_judge` evidence** — 汇总各 metric 得分与 pass/fail 结果的一条 evidence，与其他 evaluation 一样被 cell 的 `evaluation_refs` 引用。

cell 结果中还记录了 `conversation_turns`（本次会话共进行了多少轮）以及指向 `conversation.json` artifact 的 `conversation_ref`，因此你可以从结果矩阵或报告中直接追溯到完整对话记录。

## 下一步

- [评估与打分](/zh/guide/evaluation) — 单轮 task 的三层评估流水线如何工作
- [task.yaml Schema](/zh/reference/task-yaml) — 包含 `scenario`、`expected_outcome`、`user_description` 的完整字段参考
- [eval.yaml Schema](/zh/reference/eval-yaml) — 完整的 `JudgeConfig` 参考
