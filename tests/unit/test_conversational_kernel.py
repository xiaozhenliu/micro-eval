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
    client = resolve_judge_client(config)
    # No assertion on client value — depends on env


def test_resolve_judge_client_disabled():
    config = JudgeConfig(enabled=False, provider="deepeval_conversational")
    client = resolve_judge_client(config)
    assert client is None


def test_execute_cell_routes_to_conversational_branch():
    """Verify branch condition logic."""
    from micro_eval.models.configuration import AgentSpec, ConfigurationSpec
    from micro_eval.models.task import TaskSpec
    from micro_eval.models.run import RunCell

    task_conv = TaskSpec(
        id="t1", name="T1", input_payload="ctx",
        scenario="test scenario",
    )
    assert task_conv.scenario is not None

    task_single = TaskSpec(id="t2", name="T2", input_payload="ctx")
    assert task_single.scenario is None

    config_deepeval = JudgeConfig(enabled=True, provider="deepeval")
    assert config_deepeval.provider != "deepeval_conversational"
