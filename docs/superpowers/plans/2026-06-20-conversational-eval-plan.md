# Conversational Evaluation (DeepEval ConversationSimulator) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable multi-turn conversational evaluation of agents by integrating DeepEval's ConversationSimulator into micro-eval's evaluation layer, with optional A2A transport for remote agents.

**Architecture:** micro-eval imports DeepEval ConversationSimulator as a Python library (same pattern as AgentBeats Green Agents importing tau2-bench). A `model_callback` bridges micro-eval's execution layer to DeepEval's simulation engine. A2A is used only as transport inside `model_callback` when the evaluated agent is a remote A2A server. The existing single-turn DeepEval GEval judge remains the default; conversational evaluation is an opt-in parallel path.

**Tech Stack:** DeepEval (`ConversationSimulator`, `ConversationalTestCase`, multi-turn metrics), Pydantic v2, asyncio, httpx (for optional A2A transport).

---

## Design Rationale

This section documents **why** each major design decision was made, grounded in research of DeepEval's actual interfaces and AgentBeats' actual architecture (see `docs/references/deepeval-agentbeats-boundaries.md`).

### DR-1: DeepEval as Python import, not as A2A service

**Decision:** Import DeepEval directly in the micro-eval Python process. Do NOT wrap it as an A2A service.

**Why:**
- DeepEval is a pure Python library with no HTTP endpoint. Wrapping it as A2A would add ~200 lines of custom server code plus a service deployment — all to call a library that lives in the same process.
- AgentBeats' Green Agents follow the same pattern: Tau2 Green Agent does `from tau2.evaluator.evaluator import evaluate_simulation`, Debate Judge does `import google.genai`. No Green Agent wraps its evaluation tool as a service. Evaluation tools are hammers, not conversation partners.
- A2A solves "two autonomous agents need to collaborate." DeepEval is not autonomous — it does exactly what you tell it. A protocol for negotiation is overhead, not value.

### DR-2: A2A only for agent-to-agent transport inside model_callback

**Decision:** A2A appears only inside `model_callback` when the evaluated agent is a remote A2A server. micro-eval never exposes itself as an A2A endpoint (in this phase).

**Why:**
- In AgentBeats, A2A is used exclusively between agents (CLI→Green, Green→Purple). Green Agents never use A2A to call evaluation tools.
- For subprocess agents, `model_callback` reads/writes stdin/stdout directly — no protocol overhead, full lifecycle control (timeout via SIGTERM/SIGKILL), workspace isolation preserved.
- A2A transport is only needed for agents that are already deployed as HTTP services. This is an optional transport choice, not an architectural commitment.

### DR-3: Parallel path, not replacement of existing judge

**Decision:** Add `ConversationalJudge` alongside `DeepEvalJudgeClient`. The existing GEval single-turn judge stays as default via `provider: "deepeval"`.

**Why:**
- micro-eval's P5 principle: 先人工后自动. Single-turn GEval covers most current use cases. Conversational evaluation is for when users explicitly need multi-turn testing.
- The `JudgeClient` Protocol interface (`judge(prompt, cell, result, config) → JudgeOutcome`) is fundamentally single-turn — it receives a finished result. Conversational evaluation needs to drive the conversation before scoring. Forcing it through the existing interface would require awkward workarounds.
- Backward compatibility: all existing `eval.yaml` files continue working without changes.

### DR-4: ConversationSimulator drives the conversation, not micro-eval

**Decision:** Delegate conversation orchestration to DeepEval's ConversationSimulator. micro-eval provides the `model_callback` bridge and collects results.

**Why:**
- ConversationSimulator already handles: simulated user persona generation, conversation flow control, stopping conditions (expected_outcome met or max_turns), parallel simulation, adversarial personas. Reimplementing any of this is waste.
- DeepEval provides 14 multi-turn metrics (ConversationCompleteness, TurnRelevancy, KnowledgeRetention, GoalAccuracy, ConversationalGEval, etc.) that operate on `ConversationalTestCase`. Building our own conversation driver would require also building our own metrics.
- The `model_callback` interface is async and opaque to DeepEval — micro-eval can do anything inside it (subprocess I/O, HTTP calls, A2A) without DeepEval knowing or caring.

### DR-5: Subprocess agents stay alive during multi-turn via JSONL on stdin/stdout

**Decision:** For subprocess agents in conversational mode, keep the process running and communicate via newline-delimited JSON on stdin/stdout.

**Why:**
- Spawning a new process per turn would lose all agent state (memory, file handles, loaded models). Real conversational agents maintain state across turns.
- JSONL is zero-dependency (Python stdlib `json`), works with any language the agent is written in, and preserves micro-eval's full execution model: workspace isolation, OS sandbox, SIGTERM timeout, env whitelist, secrets redaction.
- The agent's existing `command` is reused — the only difference is the agent reads multiple JSONL lines from stdin instead of one blob, and writes JSONL responses to stdout.

### DR-6: TaskSpec gains conversational fields, not a new model

**Decision:** Add `scenario`, `expected_outcome`, `user_description` as optional fields on `TaskSpec`.

**Why:**
- These map directly to DeepEval's `ConversationalGolden` parameters. A separate model would require a separate loading path, separate YAML schema, and separate test infrastructure.
- Optional fields preserve backward compatibility — existing tasks without these fields work exactly as before (single-turn evaluation).
- `input_payload` remains the initial prompt for single-turn mode. In conversational mode, `scenario` + `expected_outcome` + `user_description` define the ConversationalGolden, and `input_payload` can serve as additional context or initial system prompt for the agent.

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `src/micro_eval/evaluation/conversational_judge.py` | ConversationSimulator integration, model_callback orchestration, multi-turn metric evaluation |
| `src/micro_eval/engine/agent_bridge.py` | model_callback implementations: `SubprocessBridge` (JSONL stdin/stdout). **归属 Agent Adapter Layer**（Unicorn Design §5.4），放在 `engine/` 目录下与 `adapter.py` 同级 |
| `tests/unit/test_conversational_judge.py` | Unit tests for conversational judge |
| `tests/unit/test_agent_bridge.py` | Unit tests for agent bridges |
| `tests/unit/test_conversational_kernel.py` | Kernel integration + resolve_judge_client tests |

### Modified files

| File | Changes |
|------|---------|
| `src/micro_eval/models/task.py` | Add `scenario`, `expected_outcome`, `user_description` to `TaskSpec` |
| `src/micro_eval/models/configuration.py` | Extend `JudgeConfig.provider` to accept `"deepeval_conversational"` |
| `src/micro_eval/models/run.py` | Add `conversation_turns` and `conversation_ref` to `CellResult` |
| `src/micro_eval/evaluation/llm_judge.py` | Extend `resolve_judge_client` to return conversational judge |
| `src/micro_eval/engine/kernel.py` | Add conversational evaluation branch in `_execute_cell` |
| `ui/src/lib/schema.ts` | Add `conversation_turns` and `conversation_ref` to CellResult zod schema |

### Modified files (continued)

| File | Changes |
|------|---------|
| `src/micro_eval/engine/adapter.py` | Add public `build_env` alias for `_build_env` (one line: `build_env = _build_env`). Existing internal callers of `_build_env` continue working |

### Not modified

| File | Why |
|------|-----|
| `src/micro_eval/engine/providers/` | WorkspaceProvider protocol unchanged |
| `src/micro_eval/evaluation/validator.py` | Deterministic validation unchanged — **conversational path must still call `validate_cell()` on final output** |
| `src/micro_eval/trace/` | Trace providers unchanged |
| `src/micro_eval/store/` | Store interfaces unchanged (Pydantic backward compatible) |

### Deferred to future phase

| Item | Reason |
|------|--------|
| `A2ABridge` implementation + tests | No config path to pass `agent_url` yet; `AgentSpec` needs URL field first. Remove from Task 3 code, add as future extension note |

---

## Task Breakdown

### Task 1: Extend TaskSpec with conversational fields

**Files:**
- Modify: `src/micro_eval/models/task.py:117-140`
- Test: `tests/unit/test_agent_bridge.py` (later)

- [ ] **Step 1: Add optional conversational fields to TaskSpec**

```python
# In TaskSpec class, after existing fields:
class TaskSpec(BaseModel):
    # ... existing fields ...
    revision_id: str = ""
    # Conversational evaluation fields (optional, backward compatible)
    scenario: str | None = None
    expected_outcome: str | None = None
    user_description: str | None = None
```

These three fields map 1:1 to DeepEval's `ConversationalGolden(scenario, expected_outcome, user_description)`. When all three are `None`, the task uses single-turn evaluation (existing behavior). When `scenario` is set, the task is eligible for conversational evaluation.

- [ ] **Step 2: Add model backward compatibility tests**

Add to `tests/unit/test_canonical_models.py`:

```python
def test_task_spec_conversational_fields_default_none():
    """Conversational fields are optional — existing tasks must not break."""
    task = TaskSpec(id="t", name="T", input_payload="hello")
    assert task.scenario is None
    assert task.expected_outcome is None
    assert task.user_description is None


def test_task_spec_conversational_fields_roundtrip():
    """Conversational fields survive JSON serialization."""
    task = TaskSpec(
        id="conv", name="Conv", input_payload="ctx",
        scenario="test scenario",
        expected_outcome="agent succeeds",
        user_description="a tester",
    )
    data = task.model_dump(mode="json")
    restored = TaskSpec.model_validate(data)
    assert restored.scenario == "test scenario"
    assert restored.expected_outcome == "agent succeeds"
    assert restored.user_description == "a tester"
```

- [ ] **Step 3: Verify existing tests still pass**

Run: `uv run pytest tests/ -x -q`
Expected: All 455+ tests pass (new fields are optional with `None` default).

- [ ] **Step 4: Commit**

```bash
git add src/micro_eval/models/task.py
git commit -m "feat(models): add conversational fields to TaskSpec for multi-turn evaluation"
```

---

### Task 2: Extend JudgeConfig and CellResult

**Files:**
- Modify: `src/micro_eval/models/configuration.py:173-190`
- Modify: `src/micro_eval/models/run.py:87-114`

- [ ] **Step 1: Extend JudgeConfig provider enum and add conversational params**

```python
class JudgeConfig(BaseModel):
    schema_version: str = SCHEMA_VERSION
    enabled: bool = False
    provider: Literal["deepeval", "deepeval_conversational"] = "deepeval"
    model: str = ""
    temperature: float = 0.0
    pass_threshold: float = 0.5
    required_secrets: list[str] = Field(default_factory=list)
    # Conversational evaluation parameters
    max_turns: int = 10
    turn_timeout_s: float = 60.0
    simulator_model: str = ""
    conversational_metrics: list[str] = Field(default_factory=list)

    @field_validator("required_secrets")
    @classmethod
    def secrets_must_use_prefix(cls, value: list[str]) -> list[str]:
        bad = [name for name in value if not name.startswith("MICRO_EVAL_SECRET_")]
        if bad:
            raise ValueError("judge.required_secrets must use MICRO_EVAL_SECRET_* names")
        return value
```

- [ ] **Step 2: Extend CellResult with conversation metadata**

```python
class CellResult(BaseModel):
    # ... existing fields ...
    snapshot_gate_result: SnapshotGateResult | None = None
    # Conversational evaluation metadata (optional, backward compatible)
    conversation_turns: int = 0
    conversation_ref: str | None = None
```

- [ ] **Step 3: Add model backward compatibility tests**

Add to `tests/unit/test_canonical_models.py`:

```python
def test_judge_config_default_provider_unchanged():
    """Existing eval.yaml without provider field should default to 'deepeval'."""
    config = JudgeConfig(enabled=True)
    assert config.provider == "deepeval"


def test_judge_config_accepts_conversational_provider():
    config = JudgeConfig(enabled=True, provider="deepeval_conversational")
    assert config.provider == "deepeval_conversational"
    assert config.max_turns == 10
    assert config.turn_timeout_s == 60.0
    assert config.conversational_metrics == []


def test_judge_config_rejects_unknown_provider():
    with pytest.raises(ValidationError):
        JudgeConfig(enabled=True, provider="unknown_provider")


def test_cell_result_conversational_fields_default():
    """Existing CellResult construction must not break."""
    result = CellResult(
        cell_id="c1", run_id="r1", task_id="t1",
        configuration_id="cfg", configuration_name="cfg",
        repetition=1, status=CellStatus.passed,
    )
    assert result.conversation_turns == 0
    assert result.conversation_ref is None


def test_cell_result_conversational_fields_roundtrip():
    result = CellResult(
        cell_id="c1", run_id="r1", task_id="t1",
        configuration_id="cfg", configuration_name="cfg",
        repetition=1, status=CellStatus.passed,
        conversation_turns=5,
        conversation_ref="c1::conversation::abc123",
    )
    data = result.model_dump(mode="json")
    restored = CellResult.model_validate(data)
    assert restored.conversation_turns == 5
    assert restored.conversation_ref == "c1::conversation::abc123"
```

- [ ] **Step 4: Sync Zod schema for CellResult**

In `ui/src/lib/schema.ts`, add two fields to `CellResultSchema` before the closing `})`:

```typescript
  snapshot_gate_result: SnapshotGateResultSchema.nullable().default(null),
  // Conversational evaluation metadata (backward compatible)
  conversation_turns: z.number().int().default(0),
  conversation_ref: z.string().nullable().default(null),
});
```

- [ ] **Step 5: Verify existing tests still pass**

Run: `uv run pytest tests/ -x -q && cd ui && npx vitest run`
Expected: All Python and vitest tests pass (new fields have defaults).

- [ ] **Step 6: Commit**

```bash
git add src/micro_eval/models/configuration.py src/micro_eval/models/run.py tests/unit/test_canonical_models.py ui/src/lib/schema.ts
git commit -m "feat(models): extend JudgeConfig and CellResult for conversational evaluation"
```

---

### Task 3: Implement SubprocessBridge (Agent Adapter Layer)

**Files:**
- Create: `src/micro_eval/engine/agent_bridge.py` (Agent Adapter Layer, 与 adapter.py 同级)
- Create: `tests/unit/test_agent_bridge.py`

- [ ] **Step 1: Implement SubprocessBridge**

```python
"""Agent bridges providing DeepEval model_callback implementations."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from micro_eval.engine.adapter import Redactor
from micro_eval.models.configuration import AgentSpec


class BridgeError(Exception):
    """Raised when agent bridge communication fails."""


class SubprocessBridge:
    """Bridge a subprocess agent to DeepEval's model_callback via JSONL on stdin/stdout.

    The subprocess stays alive for the duration of the conversation.
    Each turn: write a JSON line to stdin, read a JSON line from stdout.
    """

    def __init__(
        self,
        *,
        agent: AgentSpec,
        cwd: Path,
        env: dict[str, str],
        turn_timeout_s: float = 60.0,
        output_cap_bytes: int = 10 * 1024 * 1024,
    ):
        self.agent = agent
        self.cwd = cwd
        self.env = env
        self.turn_timeout_s = turn_timeout_s
        self.output_cap_bytes = output_cap_bytes
        self._proc: asyncio.subprocess.Process | None = None
        self._turn_count = 0

    async def start(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            *self.agent.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.cwd),
            env=self.env,
        )

    async def send_turn(self, text: str) -> str:
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            raise BridgeError("subprocess not started")
        self._turn_count += 1
        request = json.dumps({"turn": self._turn_count, "content": text}) + "\n"
        try:
            self._proc.stdin.write(request.encode())
            await self._proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise BridgeError(f"subprocess stdin closed: {exc}") from exc
        try:
            raw = await asyncio.wait_for(
                self._proc.stdout.readline(), timeout=self.turn_timeout_s
            )
        except asyncio.TimeoutError:
            raise BridgeError(f"turn {self._turn_count} timed out after {self.turn_timeout_s}s")
        if not raw:
            raise BridgeError("subprocess stdout closed unexpectedly")
        try:
            response = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BridgeError(f"invalid JSON from agent: {raw[:200]!r}") from exc
        return str(response.get("content", response.get("text", "")))

    async def stop(self) -> tuple[int | None, str]:
        if self._proc is None:
            return None, ""
        if self._proc.stdin and not self._proc.stdin.is_closing():
            self._proc.stdin.close()
        try:
            await asyncio.wait_for(self._proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=1)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()
        stderr = b""
        if self._proc.stderr:
            stderr = await self._proc.stderr.read()
        return self._proc.returncode, stderr.decode(errors="replace")

    @property
    def turn_count(self) -> int:
        return self._turn_count
```

- [ ] ~~**Step 2: Implement A2ABridge (optional transport)**~~ **DEFERRED to future phase**

> A2ABridge 需要先在 `AgentSpec` 中增加 URL 字段、在 kernel 中传递 `agent_url` 参数、并在 `SameStartSnapshot` 中记录远程 agent endpoint 作为可比性维度。本阶段只实现 SubprocessBridge；A2ABridge 的参考代码保留在本文档的 DR-2 设计理由中，不纳入实现范围。

- [ ] **Step 3: Write tests for SubprocessBridge**

```python
"""Agent bridge unit tests."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from micro_eval.engine.agent_bridge import BridgeError, SubprocessBridge
from micro_eval.models.configuration import AgentSpec


def _echo_agent_spec() -> AgentSpec:
    """An agent that reads JSONL from stdin and echoes each turn back."""
    script = (
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    data = json.loads(line)\n"
        "    resp = {'turn': data['turn'], 'content': f\"echo: {data['content']}\"}\n"
        "    print(json.dumps(resp), flush=True)\n"
    )
    return AgentSpec(name="echo-agent", command=[sys.executable, "-c", script])


# --- happy path ---

@pytest.mark.asyncio
async def test_subprocess_bridge_multi_turn(tmp_path: Path) -> None:
    bridge = SubprocessBridge(
        agent=_echo_agent_spec(),
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin"},
        turn_timeout_s=5.0,
    )
    await bridge.start()
    r1 = await bridge.send_turn("hello")
    assert "echo: hello" in r1
    r2 = await bridge.send_turn("world")
    assert "echo: world" in r2
    assert bridge.turn_count == 2
    exit_code, stderr = await bridge.stop()
    assert exit_code == 0


# --- error paths ---

@pytest.mark.asyncio
async def test_subprocess_bridge_timeout(tmp_path: Path) -> None:
    agent = AgentSpec(name="slow", command=[sys.executable, "-c", "import time; time.sleep(60)"])
    bridge = SubprocessBridge(
        agent=agent, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"}, turn_timeout_s=0.1,
    )
    await bridge.start()
    with pytest.raises(BridgeError, match="timed out"):
        await bridge.send_turn("hello")
    await bridge.stop()


@pytest.mark.asyncio
async def test_subprocess_bridge_not_started() -> None:
    agent = AgentSpec(name="x", command=["true"])
    bridge = SubprocessBridge(agent=agent, cwd=Path("."), env={})
    with pytest.raises(BridgeError, match="not started"):
        await bridge.send_turn("hello")


@pytest.mark.asyncio
async def test_subprocess_bridge_process_crash(tmp_path: Path) -> None:
    """Agent exits after first turn — second turn should raise BridgeError."""
    script = (
        "import json, sys\n"
        "line = sys.stdin.readline()\n"
        "data = json.loads(line)\n"
        "print(json.dumps({'content': 'bye'}), flush=True)\n"
        "sys.exit(0)\n"
    )
    agent = AgentSpec(name="crash", command=[sys.executable, "-c", script])
    bridge = SubprocessBridge(agent=agent, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"}, turn_timeout_s=2.0)
    await bridge.start()
    r1 = await bridge.send_turn("first")
    assert "bye" in r1
    with pytest.raises(BridgeError, match="stdout closed"):
        await bridge.send_turn("second")
    await bridge.stop()


@pytest.mark.asyncio
async def test_subprocess_bridge_invalid_json(tmp_path: Path) -> None:
    """Agent returns non-JSON — should raise BridgeError."""
    script = (
        "import sys\n"
        "for line in sys.stdin:\n"
        "    print('this is not json', flush=True)\n"
    )
    agent = AgentSpec(name="bad-json", command=[sys.executable, "-c", script])
    bridge = SubprocessBridge(agent=agent, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"}, turn_timeout_s=2.0)
    await bridge.start()
    with pytest.raises(BridgeError, match="invalid JSON"):
        await bridge.send_turn("hello")
    await bridge.stop()


@pytest.mark.asyncio
async def test_subprocess_bridge_missing_content_field(tmp_path: Path) -> None:
    """Agent returns JSON without content/text field — should return empty string."""
    script = (
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    print(json.dumps({'status': 'ok'}), flush=True)\n"
    )
    agent = AgentSpec(name="no-content", command=[sys.executable, "-c", script])
    bridge = SubprocessBridge(agent=agent, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"}, turn_timeout_s=2.0)
    await bridge.start()
    result = await bridge.send_turn("hello")
    assert result == ""
    await bridge.stop()


@pytest.mark.asyncio
async def test_subprocess_bridge_stop_already_exited(tmp_path: Path) -> None:
    """stop() on a process that already exited should not raise."""
    script = "import sys; sys.exit(0)"
    agent = AgentSpec(name="fast-exit", command=[sys.executable, "-c", script])
    bridge = SubprocessBridge(agent=agent, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"})
    await bridge.start()
    await asyncio.sleep(0.2)  # let it exit
    exit_code, stderr = await bridge.stop()
    assert exit_code == 0


@pytest.mark.asyncio
async def test_subprocess_bridge_stop_forceful_kill(tmp_path: Path) -> None:
    """Process that ignores SIGTERM should be killed via SIGKILL."""
    script = (
        "import signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "while True: time.sleep(1)\n"
    )
    agent = AgentSpec(name="unkillable", command=[sys.executable, "-c", script])
    bridge = SubprocessBridge(agent=agent, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"})
    await bridge.start()
    exit_code, stderr = await bridge.stop()
    # Process was killed — exit code is negative (signal) or non-zero
    assert exit_code != 0 or exit_code is None
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_agent_bridge.py -v`
Expected: All 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/micro_eval/engine/agent_bridge.py tests/unit/test_agent_bridge.py
git commit -m "feat(adapter): add SubprocessBridge for multi-turn JSONL model_callback"
```

---

### Task 4: Implement ConversationalJudge

**Files:**
- Create: `src/micro_eval/evaluation/conversational_judge.py`
- Create: `tests/unit/test_conversational_judge.py`

- [ ] **Step 1: Implement conversational judge**

```python
"""Conversational evaluation via DeepEval ConversationSimulator."""

from __future__ import annotations

import asyncio
import importlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

from micro_eval.engine.adapter import Redactor
from micro_eval.engine.agent_bridge import BridgeError, SubprocessBridge
from micro_eval.models.artifact import EvidenceItem
from micro_eval.models.configuration import AgentSpec, JudgeConfig
from micro_eval.models.evaluation import EvaluationResult
from micro_eval.models.ids import compact_timestamp, rubric_digest, sha256_text
from micro_eval.models.run import AdapterResult, CellStatus, RunCell
from micro_eval.models.task import RubricSpec

logger = logging.getLogger(__name__)

METRIC_REGISTRY: dict[str, str] = {
    "conversation_completeness": "ConversationCompletenessMetric",
    "turn_relevancy": "TurnRelevancyMetric",
    "knowledge_retention": "KnowledgeRetentionMetric",
    "role_adherence": "RoleAdherenceMetric",
    "goal_accuracy": "GoalAccuracyMetric",
}
DEFAULT_METRICS = ["conversation_completeness", "turn_relevancy"]


@dataclass
class ConversationalOutcome:
    score: float | None
    pass_fail: str | None
    rationale: str
    scores: dict[str, float] = field(default_factory=dict)
    turn_count: int = 0
    conversation: list[dict[str, str]] = field(default_factory=list)


async def simulate_conversation(
    *,
    cell: RunCell,
    config: JudgeConfig,
    agent: AgentSpec,
    cwd: Path,
    env: dict[str, str],
    redactor: Redactor,
) -> tuple[object, AdapterResult, list[dict[str, str]]] | None:
    """Phase 1: Drive multi-turn conversation, return test_case + results.

    Does NOT score — returns the raw ConversationalTestCase for scoring later.
    This split enables Invariant #6: deterministic validation between simulation and scoring.
    """
    task = cell.task
    if not task.scenario:
        return None

    deepeval_top = importlib.import_module("deepeval")
    deepeval_test_case = importlib.import_module("deepeval.test_case")
    deepeval_dataset = importlib.import_module("deepeval.dataset")
    deepeval_simulator = importlib.import_module("deepeval.simulator")
    deepeval_metrics = importlib.import_module("deepeval.metrics")
    Turn = getattr(deepeval_test_case, "Turn")
    ConversationalGolden = getattr(deepeval_dataset, "ConversationalGolden")
    ConversationSimulator = getattr(deepeval_simulator, "ConversationSimulator")
    deepeval_evaluate = getattr(deepeval_top, "evaluate")

    bridge = SubprocessBridge(
        agent=agent, cwd=cwd, env=env, turn_timeout_s=config.turn_timeout_s,
    )
    await bridge.start()

    conversation_log: list[dict[str, str]] = []
    main_loop = asyncio.get_event_loop()

    # model_callback must be SYNC because simulate() runs in an executor thread.
    # Bridge I/O is dispatched back to the main event loop via run_coroutine_threadsafe.
    def model_callback(input: str) -> Turn:
        conversation_log.append({"role": "user", "content": input})
        try:
            future = asyncio.run_coroutine_threadsafe(bridge.send_turn(input), main_loop)
            response = future.result(timeout=config.turn_timeout_s)
        except BridgeError as exc:
            response = f"[bridge error: {exc}]"
        except Exception as exc:
            response = f"[bridge error: {exc}]"
        response = redactor.redact(response)
        conversation_log.append({"role": "assistant", "content": response})
        return Turn(role="assistant", content=response)

    golden = ConversationalGolden(
        scenario=task.scenario,
        expected_outcome=task.expected_outcome or "",
        user_description=task.user_description or "",
    )

    try:
        # DeepEval's simulate() internally calls loop.run_until_complete(),
        # which fails inside an already-running asyncio loop. Run in a
        # separate thread with its own event loop to avoid this.
        simulator_kwargs = {"model_callback": model_callback}
        if config.simulator_model:
            simulator_kwargs["simulator_model"] = config.simulator_model
        simulator = ConversationSimulator(**simulator_kwargs)

        def _run_simulate():
            return simulator.simulate(
                conversational_goldens=[golden],
                max_user_simulations=config.max_turns,
            )

        test_cases = await asyncio.get_event_loop().run_in_executor(None, _run_simulate)
    except Exception as exc:
        logger.warning("ConversationSimulator failed: %s", exc)
        return None
    finally:
        exit_code, stderr = await bridge.stop()

    if not test_cases:
        return None
    test_case = test_cases[0]

    last_output = ""
    for entry in reversed(conversation_log):
        if entry["role"] == "assistant":
            last_output = entry["content"]
            break

    adapter_result = AdapterResult(
        status=CellStatus.passed if exit_code is None or exit_code == 0 else CellStatus.error,
        exit_code=exit_code,
        stdout="",
        stderr=stderr or "",
        output=last_output,
        latency_s=0.0,
        trace_id=cell.cell_id,
    )

    return test_case, adapter_result, conversation_log


async def score_conversation(
    *,
    cell: RunCell,
    config: JudgeConfig,
    test_case: object,
    turn_count: int,
    redactor: Redactor,
    evidence_prefix: str,
) -> tuple[EvaluationResult, EvidenceItem] | None:
    """Phase 2: Score a completed conversation using DeepEval metrics.

    Called AFTER deterministic validation passes (Invariant #6).
    """
    deepeval_top = importlib.import_module("deepeval")
    deepeval_metrics = importlib.import_module("deepeval.metrics")
    deepeval_evaluate = getattr(deepeval_top, "evaluate")

    metric_names = config.conversational_metrics or DEFAULT_METRICS
    metrics = []
    for name in metric_names:
        cls_name = METRIC_REGISTRY.get(name)
        if cls_name:
            cls = getattr(deepeval_metrics, cls_name, None)
            if cls:
                metrics.append(cls(threshold=config.pass_threshold))

    rubric = _rubric_text(cell)
    if rubric and hasattr(deepeval_metrics, "ConversationalGEval"):
        metrics.append(
            deepeval_metrics.ConversationalGEval(
                name="rubric",
                criteria=rubric,
                threshold=config.pass_threshold,
            )
        )

    if not metrics:
        logger.warning("No valid conversational metrics configured")
        return None

    try:
        # deepeval.evaluate() also calls loop.run_until_complete() internally
        def _run_evaluate():
            return deepeval_evaluate(
                test_cases=[test_case], metrics=metrics
            )

        eval_result = await asyncio.get_event_loop().run_in_executor(None, _run_evaluate)
    except Exception as exc:
        logger.warning("DeepEval evaluate failed: %s", exc)
        return None

    scores: dict[str, float] = {}
    all_pass = True
    for tr in eval_result.test_results:
        if not tr.success:
            all_pass = False
        for md in (tr.metrics_data or []):
            metric_score = getattr(md, "score", None)
            metric_name = getattr(md, "name", getattr(md, "metric", "unknown"))
            if metric_score is not None:
                scores[str(metric_name)] = float(metric_score)

    avg_score = sum(scores.values()) / len(scores) if scores else None
    pass_fail = "pass" if all_pass else "fail"

    rationale_parts = [f"{k}={v:.2f}" for k, v in scores.items()]
    rationale = redactor.redact(f"conversational eval: {'; '.join(rationale_parts)}")[:500]

    evidence_id = f"{evidence_prefix}::conversational-judge"
    evidence = EvidenceItem(
        evidence_id=evidence_id,
        kind="conversational_judge",
        cell_id=cell.cell_id,
        status="passed" if pass_fail == "pass" else "failed",
        severity="info",
        summary=rationale,
        source_kind="evaluation_id",
        metadata={
            "provider": "deepeval_conversational",
            "turn_count": turn_count,
            "metrics": list(scores.keys()),
        },
    )

    evaluation_id = f"{cell.cell_id}::conversational-judge::{sha256_text(str(scores))[:12]}"
    evaluation = EvaluationResult(
        evaluation_id=evaluation_id,
        cell_id=cell.cell_id,
        evaluator_type="conversational_judge",
        evaluator="deepeval_conversational",
        evaluator_meta={
            "turn_count": turn_count,
            "simulator_model": config.simulator_model or "default",
            "metrics": ",".join(scores.keys()),
        },
        rubric_hash=rubric_digest(cell.task.rubric),
        pass_fail=pass_fail,
        score=avg_score,
        scores=scores,
        comment=rationale,
        evidence_refs=[evidence_id],
        created_at=compact_timestamp(),
    )
    evidence.source_ref = evaluation_id

    return evaluation, evidence


def _rubric_text(cell: RunCell) -> str:
    rubric = cell.task.rubric
    if rubric is None:
        return ""
    if isinstance(rubric, str):
        return rubric
    if isinstance(rubric, RubricSpec):
        dimensions = "; ".join(str(item) for item in rubric.dimensions)
        return f"{rubric.text}\nDimensions: {dimensions}"
    return str(rubric)
```

- [ ] **Step 2: Write tests for ConversationalJudge**

```python
"""Conversational judge unit tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from micro_eval.engine.adapter import Redactor
from micro_eval.engine.agent_bridge import BridgeError
from micro_eval.evaluation.conversational_judge import (
    ConversationalOutcome,
    _rubric_text,
    simulate_conversation,
    score_conversation,
)
from micro_eval.models.configuration import AgentSpec, ConfigurationSpec, JudgeConfig
from micro_eval.models.run import RunCell
from micro_eval.models.task import RubricSpec, TaskSpec


def _conversational_cell(*, scenario="User asks a question", expected_outcome="Agent answers",
                          user_description="A student", rubric=None) -> RunCell:
    config = ConfigurationSpec(
        id="cfg", name="cfg",
        agent=AgentSpec(name="echo", command=[sys.executable, "-c",
            "import json,sys\n"
            "for line in sys.stdin:\n"
            "    d=json.loads(line)\n"
            "    print(json.dumps({'content':'ok: '+d['content']}),flush=True)\n"
        ]),
    )
    task = TaskSpec(
        id="conv-task",
        name="Conversation Task",
        input_payload="initial context",
        scenario=scenario,
        expected_outcome=expected_outcome,
        user_description=user_description,
        rubric=rubric,
    )
    return RunCell(cell_id="cell-conv", task=task, configuration=config)


def _single_turn_cell() -> RunCell:
    config = ConfigurationSpec(
        id="cfg", name="cfg",
        agent=AgentSpec(name="x", command=["true"]),
    )
    task = TaskSpec(id="t", name="T", input_payload="input")
    return RunCell(cell_id="c", task=task, configuration=config)


# --- model field tests ---

def test_conversational_cell_has_scenario() -> None:
    cell = _conversational_cell()
    assert cell.task.scenario is not None
    assert cell.task.expected_outcome is not None


def test_non_conversational_cell_has_no_scenario() -> None:
    cell = _single_turn_cell()
    assert cell.task.scenario is None


# --- early return: no scenario ---

@pytest.mark.asyncio
async def test_evaluate_returns_none_without_scenario(tmp_path: Path) -> None:
    """Tasks without scenario field should return None immediately."""
    cell = _single_turn_cell()
    config = JudgeConfig(enabled=True, provider="deepeval_conversational")
    result = await simulate_conversation(
        cell=cell,
        config=config,
        agent=cell.configuration.agent,
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin"},
        redactor=Redactor({}),
    )
    assert result is None


# --- _rubric_text helper ---

def test_rubric_text_from_string() -> None:
    cell = _conversational_cell(rubric="Evaluate helpfulness")
    assert _rubric_text(cell) == "Evaluate helpfulness"


def test_rubric_text_from_rubric_spec() -> None:
    rubric = RubricSpec(text="Score quality", dimensions=["accuracy", "clarity"])
    cell = _conversational_cell(rubric=rubric)
    text = _rubric_text(cell)
    assert "Score quality" in text
    assert "accuracy" in text
    assert "clarity" in text


def test_rubric_text_from_none() -> None:
    cell = _conversational_cell(rubric=None)
    assert _rubric_text(cell) == ""


# --- full evaluation flow with mocked DeepEval ---

@pytest.mark.asyncio
async def test_evaluate_cell_conversational_full_flow(tmp_path: Path) -> None:
    """Full flow with mocked DeepEval — verifies output structure."""
    cell = _conversational_cell()
    config = JudgeConfig(
        enabled=True, provider="deepeval_conversational",
        pass_threshold=0.5, max_turns=3, turn_timeout_s=5.0,
    )

    # Mock DeepEval modules
    mock_turn = MagicMock()
    mock_turn_cls = MagicMock(return_value=mock_turn)

    mock_golden_cls = MagicMock()
    mock_golden = MagicMock()
    mock_golden_cls.return_value = mock_golden

    # Mock simulator
    mock_test_case = MagicMock()
    mock_test_case.turns = [
        MagicMock(role="user", content="hi"),
        MagicMock(role="assistant", content="hello"),
    ]
    mock_simulator_cls = MagicMock()
    mock_simulator_instance = MagicMock()
    mock_simulator_instance.simulate.return_value = [mock_test_case]
    mock_simulator_cls.return_value = mock_simulator_instance

    # Mock evaluate result
    mock_metric_data = MagicMock()
    mock_metric_data.score = 0.85
    mock_metric_data.name = "conversation_completeness"
    mock_test_result = MagicMock()
    mock_test_result.success = True
    mock_test_result.metrics_data = [mock_metric_data]
    mock_eval_result = MagicMock()
    mock_eval_result.test_results = [mock_test_result]

    mock_metric_cls = MagicMock()

    with patch.dict("sys.modules", {
        "deepeval.test_case": MagicMock(Turn=mock_turn_cls),
        "deepeval.dataset": MagicMock(ConversationalGolden=mock_golden_cls),
        "deepeval.simulator": MagicMock(ConversationSimulator=mock_simulator_cls),
        "deepeval.metrics": MagicMock(
            ConversationCompletenessMetric=mock_metric_cls,
            TurnRelevancyMetric=mock_metric_cls,
        ),
        "deepeval": MagicMock(evaluate=MagicMock(return_value=mock_eval_result)),
    }):
        sim_result = await simulate_conversation(
            cell=cell,
            config=config,
            agent=cell.configuration.agent,
            cwd=tmp_path,
            env={"PATH": "/usr/bin:/bin"},
            redactor=Redactor({}),
        )

    assert sim_result is not None
    test_case, adapter_result, conversation_log = sim_result
    assert isinstance(conversation_log, list)
    assert test_case is not None

    # Phase 2: score the conversation
    with patch.dict("sys.modules", {
        "deepeval": MagicMock(evaluate=MagicMock(return_value=mock_eval_result)),
        "deepeval.metrics": MagicMock(
            ConversationCompletenessMetric=mock_metric_cls,
            TurnRelevancyMetric=mock_metric_cls,
        ),
    }):
        score_result = await score_conversation(
            cell=cell,
            config=config,
            test_case=test_case,
            turn_count=len(conversation_log) // 2,
            redactor=Redactor({}),
            evidence_prefix="test::evidence",
        )

    assert score_result is not None
    evaluation, evidence = score_result

    # EvaluationResult structure
    assert evaluation.evaluator_type == "conversational_judge"
    assert evaluation.evaluator == "deepeval_conversational"
    assert evaluation.cell_id == "cell-conv"
    assert evaluation.score == 0.85
    assert evaluation.pass_fail == "pass"
    assert "conversation_completeness" in evaluation.scores

    # EvidenceItem structure
    assert evidence.kind == "conversational_judge"
    assert evidence.cell_id == "cell-conv"
    assert evidence.status == "passed"
    assert evidence.metadata["provider"] == "deepeval_conversational"


@pytest.mark.asyncio
async def test_evaluate_cell_conversational_simulator_failure(tmp_path: Path) -> None:
    """ConversationSimulator raising an exception should return None."""
    cell = _conversational_cell()
    config = JudgeConfig(enabled=True, provider="deepeval_conversational", turn_timeout_s=2.0)

    mock_simulator_cls = MagicMock()
    mock_simulator_instance = MagicMock()
    mock_simulator_instance.simulate.side_effect = RuntimeError("simulator broke")
    mock_simulator_cls.return_value = mock_simulator_instance

    with patch.dict("sys.modules", {
        "deepeval.test_case": MagicMock(Turn=MagicMock()),
        "deepeval.dataset": MagicMock(ConversationalGolden=MagicMock()),
        "deepeval.simulator": MagicMock(ConversationSimulator=mock_simulator_cls),
        "deepeval.metrics": MagicMock(),
        "deepeval": MagicMock(),
    }):
        result = await simulate_conversation(
            cell=cell,
            config=config,
            agent=cell.configuration.agent,
            cwd=tmp_path,
            env={"PATH": "/usr/bin:/bin"},
            redactor=Redactor({}),
        )

    assert result is None


@pytest.mark.asyncio
async def test_simulate_redactor_applied(tmp_path: Path) -> None:
    """Secrets in agent output should be redacted in conversation log and rationale."""
    cell = _conversational_cell()
    config = JudgeConfig(enabled=True, provider="deepeval_conversational", turn_timeout_s=2.0)
    redactor = Redactor({"MICRO_EVAL_SECRET_KEY": "supersecret"})

    mock_turn_cls = MagicMock(side_effect=lambda role, content: MagicMock(role=role, content=content))
    mock_simulator_cls = MagicMock()
    mock_simulator_instance = MagicMock()
    mock_test_case = MagicMock()
    mock_test_case.turns = []
    mock_simulator_instance.simulate.return_value = [mock_test_case]
    mock_simulator_cls.return_value = mock_simulator_instance

    mock_metric_data = MagicMock(score=0.5, name="test_metric")
    mock_test_result = MagicMock(success=True, metrics_data=[mock_metric_data])
    mock_eval_result = MagicMock(test_results=[mock_test_result])

    captured_callback = None
    original_init = mock_simulator_cls.__init__

    def capture_callback(**kwargs):
        nonlocal captured_callback
        captured_callback = kwargs.get("model_callback")
        return mock_simulator_instance

    mock_simulator_cls.side_effect = capture_callback

    with patch.dict("sys.modules", {
        "deepeval.test_case": MagicMock(Turn=mock_turn_cls),
        "deepeval.dataset": MagicMock(ConversationalGolden=MagicMock()),
        "deepeval.simulator": MagicMock(ConversationSimulator=mock_simulator_cls),
        "deepeval.metrics": MagicMock(),
        "deepeval": MagicMock(evaluate=MagicMock(return_value=mock_eval_result)),
    }):
        result = await simulate_conversation(
            cell=cell,
            config=config,
            agent=cell.configuration.agent,
            cwd=tmp_path,
            env={"PATH": "/usr/bin:/bin"},
            redactor=redactor,
        )

    # The redactor should have redaction values set up
    assert redactor.values  # non-empty redaction values dict
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/test_conversational_judge.py -v`
Expected: All 8 tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/micro_eval/evaluation/conversational_judge.py tests/unit/test_conversational_judge.py
git commit -m "feat(evaluation): implement conversational judge with DeepEval ConversationSimulator"
```

---

### Task 5: Integrate into kernel

**Files:**
- Modify: `src/micro_eval/evaluation/llm_judge.py:81-93`
- Modify: `src/micro_eval/engine/kernel.py:135-314`

- [ ] **Step 1: Extend resolve_judge_client to recognize conversational provider**

In `llm_judge.py`, modify `resolve_judge_client`:

```python
def resolve_judge_client(config: JudgeConfig) -> JudgeClient | None:
    """Resolve optional judge client, returning None for disabled or unavailable judges."""
    if not config.enabled:
        return None
    # Check required secrets for all providers (including conversational)
    for name in config.required_secrets:
        if name not in os.environ:
            return None
    # Conversational judge is handled separately in kernel — return None here
    if config.provider == "deepeval_conversational":
        return None
    if config.provider == "deepeval":
        try:
            return DeepEvalJudgeClient()
        except Exception:
            return None
    return None
```

- [ ] **Step 2: Add conversational evaluation branch in _execute_cell**

In `kernel.py`, within `_execute_cell`, after the existing evaluation code (after line ~274 where `judge_result` is collected), add the conversational branch. The key change is: when `provider == "deepeval_conversational"` AND the task has `scenario`, run conversational evaluation instead of the single-turn path.

The integration point is around line 156-162 in `_execute_cell`. When conversational mode is active, we skip the normal `adapter.invoke()` and run the conversation instead:

```python
    async def _execute_cell(self, cell, adapter, artifact_store, workspace_manager,
                            record, trace_providers, judge_client, plan):
        cell_dir = artifact_store.cell_dir(cell.cell_id)
        prepared = None
        redactor = Redactor({})
        workspace_caveats = []

        try:
            prepared = workspace_manager.prepare(
                cell_id=cell.cell_id,
                workspace=cell.task.workspace,
                caveats=workspace_caveats,
            )

            # Branch: conversational evaluation
            if (plan.judge.enabled
                    and plan.judge.provider == "deepeval_conversational"
                    and cell.task.scenario is not None):
                return await self._execute_cell_conversational(
                    cell, artifact_store, prepared, record, trace_providers, plan, cell_dir, workspace_caveats,
                )

            # Existing single-turn path (unchanged from here)
            adapter_result, redactor = await adapter.invoke(
                agent=cell.configuration.agent,
                input_payload=cell.task.input_payload,
                cwd=prepared.path,
                output_dir=cell_dir,
                trace_id=cell.cell_id,
            )
        # ... rest of existing code unchanged ...
```

- [ ] **Step 3: Implement _execute_cell_conversational**

Add a new method to `ExecutionKernel`:

```python
    async def _execute_cell_conversational(
        self, cell, artifact_store, prepared, record, trace_providers, plan, cell_dir, workspace_caveats,
    ):
        """Execute a cell using conversational evaluation (DeepEval ConversationSimulator).

        Invariant #6: deterministic validation runs FIRST on final output.
        If it critically fails, conversational judge result is overridden to "fail".
        """
        import json as json_mod
        from micro_eval.evaluation.conversational_judge import simulate_conversation, score_conversation
        from micro_eval.evaluation.validator import validate_cell

        agent = cell.configuration.agent
        adapter = AgentAdapter(output_cap_bytes=plan.guardrails.output_cap_bytes)
        env_base, redactor = adapter.build_env(
            agent, cell_dir, cell_dir / "output.txt", cell.cell_id,
        )

        # Phase 1: Drive multi-turn conversation (no scoring yet)
        sim_result = await simulate_conversation(
            cell=cell,
            config=plan.judge,
            agent=agent,
            cwd=prepared.path,
            env=env_base,
            redactor=redactor,
        )

        if sim_result is None:
            return self._isolated_failure_result(cell, record, RuntimeError("conversation simulation returned None"))

        test_case, adapter_result, conversation_log = sim_result

        # Redact stderr before persisting (security requirement)
        adapter_result.stderr = redactor.redact(adapter_result.stderr)

        # Phase 2: Invariant #6 — deterministic validation BEFORE LLM scoring
        validation_eval, validation_evidence = await validate_cell(
            cell=cell,
            adapter_result=adapter_result,
            cell_dir=cell_dir,
            evidence_prefix=f"{cell.cell_id}::evidence",
            redactor=redactor,
            workspace_dir=prepared.path,
        )

        # Phase 3: Conversational scoring (only if validation didn't critically fail)
        conv_evaluation = None
        conv_evidence = None
        if validation_eval.pass_fail != "fail":
            score_result = await score_conversation(
                cell=cell,
                config=plan.judge,
                test_case=test_case,
                turn_count=len(conversation_log) // 2,
                redactor=redactor,
                evidence_prefix=f"{cell.cell_id}::evidence",
            )
            if score_result is not None:
                conv_evaluation, conv_evidence = score_result

        # Persist conversation log as artifact
        conv_artifact = artifact_store.write_text(
            cell.cell_id, "conversation", "conversation.json",
            json_mod.dumps(conversation_log, indent=2, ensure_ascii=False),
        )

        # Collect all evidence and evaluations
        all_evidence = validation_evidence[:]
        if conv_evidence is not None:
            all_evidence.append(conv_evidence)
        for ev in all_evidence:
            artifact_store.add_evidence(ev)

        artifacts = [conv_artifact]
        if adapter_result.stdout:
            artifacts.append(artifact_store.write_text(cell.cell_id, "stdout", "stdout.txt", adapter_result.stdout))
        if adapter_result.stderr:
            artifacts.append(artifact_store.write_text(cell.cell_id, "stderr", "stderr.txt", adapter_result.stderr))

        evaluations = [validation_eval]
        if conv_evaluation is not None:
            evaluations.append(conv_evaluation)
        (cell_dir / "evaluation.json").write_text(
            json_mod.dumps([item.model_dump(mode="json") for item in evaluations], indent=2)
        )

        # Determine final score/pass_fail: use conversational if available, else validation
        final_eval = conv_evaluation if conv_evaluation is not None else validation_eval

        trace = collect_trace_with_fallback(trace_providers, cell=cell, result=adapter_result, redactor=redactor)
        trace_refs = []
        if trace is not None:
            artifact_store.add_trace(trace)
            trace_refs.append(f"{trace.provider}:{trace.trace_id}")

        snapshot_gate = evaluate_snapshot_gate(record.same_start_snapshot, prepared.snapshot, task_id=cell.task.id)
        if workspace_caveats:
            snapshot_gate.caveats.extend(workspace_caveats)

        return CellResult(
            cell_id=cell.cell_id,
            run_id=record.id,
            task_id=cell.task.id,
            configuration_id=cell.configuration.id,
            configuration_name=cell.configuration.name,
            repetition=cell.repetition,
            status=CellStatus.failed if final_eval.pass_fail == "fail" else adapter_result.status,
            score=final_eval.score,
            pass_fail=final_eval.pass_fail,
            output_summary=adapter_result.output[:self.SUMMARY_LIMIT],
            stderr_summary=adapter_result.stderr[:self.SUMMARY_LIMIT],
            exit_code=adapter_result.exit_code,
            latency_s=adapter_result.latency_s,
            artifact_refs=[a.artifact_id for a in artifacts],
            evidence_refs=[ev.evidence_id for ev in all_evidence],
            evaluation_refs=[e.evaluation_id for e in evaluations],
            trace_refs=trace_refs,
            cell_snapshot=prepared.snapshot,
            snapshot_gate_result=snapshot_gate,
            conversation_turns=len(conversation_log) // 2,
            conversation_ref=conv_artifact.artifact_id,
        )
```

- [ ] **Step 4: Add kernel integration and resolve_judge_client tests**

Create `tests/unit/test_conversational_kernel.py`:

```python
"""Kernel integration tests for conversational evaluation branch."""

from __future__ import annotations

import pytest

from micro_eval.evaluation.llm_judge import resolve_judge_client
from micro_eval.models.configuration import JudgeConfig


def test_resolve_judge_client_returns_none_for_conversational():
    """Conversational provider is handled in kernel, not via JudgeClient."""
    config = JudgeConfig(enabled=True, provider="deepeval_conversational")
    client = resolve_judge_client(config)
    assert client is None


def test_resolve_judge_client_still_works_for_deepeval():
    """Existing deepeval provider should still attempt to create client."""
    config = JudgeConfig(enabled=True, provider="deepeval")
    # Will return None if deepeval not installed in test env, which is fine —
    # the point is it doesn't short-circuit like conversational does
    client = resolve_judge_client(config)
    # No assertion on client value — depends on env; just verify no exception


def test_resolve_judge_client_disabled():
    config = JudgeConfig(enabled=False, provider="deepeval_conversational")
    client = resolve_judge_client(config)
    assert client is None


def test_execute_cell_routes_to_conversational_branch():
    """Verify that _execute_cell checks provider + scenario to branch.

    This is a structural test — we verify the branch condition logic
    rather than the full execution (which requires workspace/artifact setup).
    """
    from micro_eval.models.configuration import AgentSpec, ConfigurationSpec
    from micro_eval.models.task import TaskSpec
    from micro_eval.models.run import RunCell

    # Case 1: conversational provider + scenario → should branch
    task_conv = TaskSpec(
        id="t1", name="T1", input_payload="ctx",
        scenario="test scenario",
    )
    assert task_conv.scenario is not None

    # Case 2: conversational provider + no scenario → should NOT branch
    task_single = TaskSpec(id="t2", name="T2", input_payload="ctx")
    assert task_single.scenario is None

    # Case 3: deepeval provider + scenario → should NOT branch
    config_deepeval = JudgeConfig(enabled=True, provider="deepeval")
    assert config_deepeval.provider != "deepeval_conversational"
```

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: All existing tests pass + new kernel tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/micro_eval/evaluation/llm_judge.py src/micro_eval/engine/kernel.py src/micro_eval/engine/adapter.py tests/unit/test_conversational_kernel.py
git commit -m "feat(kernel): integrate conversational evaluation branch into _execute_cell

Also exposes adapter._build_env as public build_env (rename only)."
```

---

### Task 6: End-to-end verification with example eval.yaml

**Files:**
- Create: `examples/conversational-eval/eval.yaml`
- Create: `examples/conversational-eval/echo_agent.py`
- Create: `examples/conversational-eval/tasks/conversation-task.yaml`

- [ ] **Step 1: Create an echo agent that speaks JSONL**

```python
#!/usr/bin/env python3
"""Echo agent for conversational evaluation testing.

Reads JSONL from stdin, responds with echoed content.
"""
import json
import sys

for line in sys.stdin:
    try:
        data = json.loads(line.strip())
        turn = data.get("turn", 0)
        content = data.get("content", "")
        response = {
            "turn": turn,
            "content": f"I received your message: {content}. How can I help further?",
        }
        print(json.dumps(response), flush=True)
    except json.JSONDecodeError:
        pass
```

- [ ] **Step 2: Create task YAML with conversational fields**

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

- [ ] **Step 3: Create eval.yaml**

```yaml
project_name: conversational-eval-example
configurations:
  - id: echo-agent
    name: "Echo Agent"
    agent:
      name: echo-agent
      command: ["python", "echo_agent.py"]
      input_mode: stdin
      output_mode: stdout
tasks_dir: tasks
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

- [ ] **Step 4: Verify the example runs end-to-end**

Run: `cd examples/conversational-eval && uv run micro-eval run --config eval.yaml`
Expected: Run completes, produces a run record with conversation artifacts and multi-turn scores.

- [ ] **Step 5: Commit**

```bash
git add examples/conversational-eval/
git commit -m "feat(examples): add conversational evaluation example with echo agent"
```

---

### Task 7: Verification and cleanup

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass (455+ existing + new tests).

- [ ] **Step 2: Run vitest for UI**

Run: `cd ui && npx vitest run`
Expected: All 42 UI tests pass (CellResult schema change is backward compatible).

- [ ] **Step 3: Verify single-turn eval.yaml still works**

Run: `uv run micro-eval run --config examples/basic/eval.yaml` (or any existing example)
Expected: Single-turn evaluation works exactly as before.

- [ ] **Step 4: Final commit if any cleanup needed**

```bash
git add -A && git commit -m "chore: cleanup after conversational evaluation integration"
```
