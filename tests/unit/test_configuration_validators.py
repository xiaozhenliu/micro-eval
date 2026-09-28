"""Boundary and validator tests for configuration.py models."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from micro_eval.models.configuration import (
    AgentSpec,
    ConfigurationSpec,
    EvaluationContract,
    Guardrails,
    JudgeConfig,
    ProjectConfigV2,
)


# ---------------------------------------------------------------------------
# AgentSpec validators
# ---------------------------------------------------------------------------

def _base_agent(**kwargs: Any) -> AgentSpec:
    defaults: dict[str, Any] = {"name": "agent", "command": ["cat"]}
    defaults.update(kwargs)
    return AgentSpec(**defaults)


def test_agent_empty_command_raises() -> None:
    with pytest.raises(ValidationError, match="non-empty argv"):
        AgentSpec(name="bad", command=[])


def test_agent_command_with_empty_string_entry_raises() -> None:
    with pytest.raises(ValidationError, match="non-empty strings"):
        AgentSpec(name="bad", command=["cat", ""])


def test_agent_command_with_non_string_entry_raises() -> None:
    with pytest.raises(ValidationError):
        AgentSpec(name="bad", command=["cat", 42])  # type: ignore[list-item]


def test_agent_timeout_zero_raises() -> None:
    with pytest.raises(ValidationError, match="timeout_s must be positive"):
        _base_agent(timeout_s=0)


def test_agent_timeout_negative_raises() -> None:
    with pytest.raises(ValidationError, match="timeout_s must be positive"):
        _base_agent(timeout_s=-1.0)


def test_agent_required_secrets_missing_prefix_raises() -> None:
    with pytest.raises(ValidationError, match="MICRO_EVAL_SECRET_\\*"):
        _base_agent(required_secrets=["MY_SECRET"])


def test_agent_required_secrets_valid_prefix_ok() -> None:
    agent = _base_agent(required_secrets=["MICRO_EVAL_SECRET_API_KEY"])
    assert agent.required_secrets == ["MICRO_EVAL_SECRET_API_KEY"]


def test_agent_default_timeout_is_positive() -> None:
    agent = _base_agent()
    assert agent.timeout_s > 0


# ---------------------------------------------------------------------------
# ConfigurationSpec validators
# ---------------------------------------------------------------------------

def _base_config(**kwargs: Any) -> ConfigurationSpec:
    agent = _base_agent()
    defaults: dict[str, Any] = {"id": "cfg-1", "name": "Config", "agent": agent}
    defaults.update(kwargs)
    return ConfigurationSpec(**defaults)


def test_configuration_id_empty_raises() -> None:
    with pytest.raises(ValidationError, match="required"):
        _base_config(id="")


def test_configuration_id_whitespace_only_raises() -> None:
    with pytest.raises(ValidationError, match="required"):
        _base_config(id="   ")


def test_configuration_id_with_dotdot_raises() -> None:
    with pytest.raises(ValidationError, match="path-safe"):
        _base_config(id="../evil")


def test_configuration_id_with_spaces_raises() -> None:
    with pytest.raises(ValidationError, match="path-safe"):
        _base_config(id="my cfg")


def test_configuration_id_valid_chars_ok() -> None:
    cfg = _base_config(id="cfg.v1-alpha:run_0")
    assert cfg.id == "cfg.v1-alpha:run_0"


def test_configuration_repetitions_zero_raises() -> None:
    with pytest.raises(ValidationError, match="repetitions must be >= 1"):
        _base_config(repetitions=0)


def test_configuration_repetitions_negative_raises() -> None:
    with pytest.raises(ValidationError, match="repetitions must be >= 1"):
        _base_config(repetitions=-5)


def test_configuration_repetitions_one_ok() -> None:
    cfg = _base_config(repetitions=1)
    assert cfg.repetitions == 1


def test_configuration_digest_is_64_chars() -> None:
    cfg = _base_config()
    assert len(cfg.digest) == 64


def test_configuration_digest_changes_with_repetitions() -> None:
    cfg1 = _base_config(repetitions=1)
    cfg2 = _base_config(repetitions=3)
    assert cfg1.digest != cfg2.digest


# ---------------------------------------------------------------------------
# Guardrails validators
# ---------------------------------------------------------------------------

def test_guardrails_max_concurrency_zero_raises() -> None:
    with pytest.raises(ValidationError, match="max_concurrency must be >= 1"):
        Guardrails(max_concurrency=0)


def test_guardrails_max_concurrency_negative_raises() -> None:
    with pytest.raises(ValidationError, match="max_concurrency must be >= 1"):
        Guardrails(max_concurrency=-1)


def test_guardrails_max_concurrency_positive_ok() -> None:
    g = Guardrails(max_concurrency=8)
    assert g.max_concurrency == 8


# ---------------------------------------------------------------------------
# EvaluationContract validators and migration
# ---------------------------------------------------------------------------

def test_evaluation_contract_min_repetitions_zero_raises() -> None:
    with pytest.raises(ValidationError, match="min_repetitions must be >= 1"):
        EvaluationContract(min_repetitions=0)


def test_evaluation_contract_min_repetitions_negative_raises() -> None:
    with pytest.raises(ValidationError, match="min_repetitions must be >= 1"):
        EvaluationContract(min_repetitions=-1)


def test_evaluation_contract_required_evaluators_none_migrates() -> None:
    # None → default ["validator"]
    ec = EvaluationContract(required_evaluators=None)  # type: ignore[arg-type]
    assert ec.required_evaluators == ["validator"]


def test_evaluation_contract_required_evaluators_zero_migrates() -> None:
    # int 0 → ["validator"]  (value <= 0 branch, line 151)
    ec = EvaluationContract(required_evaluators=0)  # type: ignore[arg-type]
    assert ec.required_evaluators == ["validator"]


def test_evaluation_contract_required_evaluators_positive_int_migrates() -> None:
    # int 2 → ["validator", "human-1", "human-2"]  (line 151 positive branch)
    ec = EvaluationContract(required_evaluators=2)  # type: ignore[arg-type]
    assert ec.required_evaluators == ["validator", "human-1", "human-2"]


def test_evaluation_contract_required_evaluators_string_migrates() -> None:
    # single string → list  (line 153)
    ec = EvaluationContract(required_evaluators="llm-judge")  # type: ignore[arg-type]
    assert ec.required_evaluators == ["llm-judge"]


def test_evaluation_contract_denominator_policy_legacy_all_cells() -> None:
    # "all_cells" → "include_failed"  (line 159-160)
    ec = EvaluationContract(denominator_policy="all_cells")  # type: ignore[arg-type]
    assert ec.denominator_policy == "include_failed"


def test_evaluation_contract_denominator_policy_legacy_completed_cells() -> None:
    # "completed_cells" → "exclude_failed"  (line 161-162)
    ec = EvaluationContract(denominator_policy="completed_cells")  # type: ignore[arg-type]
    assert ec.denominator_policy == "exclude_failed"


def test_evaluation_contract_denominator_policy_empty_string_defaults() -> None:
    # falsy value → "include_failed"  (line 163 fallback)
    ec = EvaluationContract(denominator_policy="")  # type: ignore[arg-type]
    assert ec.denominator_policy == "include_failed"


# ---------------------------------------------------------------------------
# JudgeConfig validators
# ---------------------------------------------------------------------------

def test_judge_config_required_secrets_missing_prefix_raises() -> None:
    with pytest.raises(ValidationError, match="MICRO_EVAL_SECRET_\\*"):
        JudgeConfig(required_secrets=["OPENAI_API_KEY"])


def test_judge_config_required_secrets_valid_prefix_ok() -> None:
    jc = JudgeConfig(required_secrets=["MICRO_EVAL_SECRET_OPENAI"])
    assert jc.required_secrets == ["MICRO_EVAL_SECRET_OPENAI"]


# ---------------------------------------------------------------------------
# ProjectConfigV2 validators
# ---------------------------------------------------------------------------

def _base_project(**kwargs: Any) -> ProjectConfigV2:
    agent = _base_agent()
    cfg = ConfigurationSpec(id="cfg-1", name="Config", agent=agent)
    defaults: dict[str, Any] = {"configurations": [cfg]}
    defaults.update(kwargs)
    return ProjectConfigV2(**defaults)


def test_project_requires_at_least_one_configuration() -> None:
    with pytest.raises(ValidationError, match="at least one configuration"):
        ProjectConfigV2(configurations=[])


def test_project_configuration_ids_must_be_unique() -> None:
    agent = _base_agent()
    cfg1 = ConfigurationSpec(id="dup", name="A", agent=agent)
    cfg2 = ConfigurationSpec(id="dup", name="B", agent=agent)
    with pytest.raises(ValidationError, match="unique"):
        ProjectConfigV2(configurations=[cfg1, cfg2])


def test_project_output_dir_absolute_raises() -> None:
    with pytest.raises(ValidationError, match="relative path"):
        _base_project(output_dir="/tmp/evil")


def test_project_output_dir_dotdot_raises() -> None:
    with pytest.raises(ValidationError, match="relative path"):
        _base_project(output_dir="../outside")


def test_project_output_dir_relative_ok() -> None:
    proj = _base_project(output_dir="results/runs")
    assert proj.output_dir == "results/runs"


def test_project_two_unique_configurations_ok() -> None:
    agent = _base_agent()
    cfg1 = ConfigurationSpec(id="cfg-a", name="A", agent=agent)
    cfg2 = ConfigurationSpec(id="cfg-b", name="B", agent=agent)
    proj = ProjectConfigV2(configurations=[cfg1, cfg2])
    assert len(proj.configurations) == 2
