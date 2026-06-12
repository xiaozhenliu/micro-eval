"""Degradation and cost-ladder acceptance tests for the Langfuse trace provider."""

from __future__ import annotations

from micro_eval.engine.adapter import Redactor
from micro_eval.models.configuration import AgentSpec, ConfigurationSpec
from micro_eval.models.run import AdapterResult, CellStatus, RunCell
from micro_eval.models.task import TaskSpec
from micro_eval.trace.langfuse_provider import LangfuseProvider

SECRET_VALUE = "sk-langfuse-secret-value"


class FakeClient:
    def __init__(self, trace: dict | None) -> None:
        self._trace = trace

    def get_trace(self, trace_id: str) -> dict | None:
        return self._trace


def _cell() -> RunCell:
    config = ConfigurationSpec(id="cfg", name="cfg", agent=AgentSpec(name="agent", command=["python", "-c", "print('ok')"]))
    return RunCell(cell_id="cell-1", task=TaskSpec(id="task", name="Task", input_payload="input"), configuration=config)


def _provider(trace: dict | None, *, host: str | None = "https://langfuse.example") -> LangfuseProvider:
    provider = LangfuseProvider.__new__(LangfuseProvider)
    provider.host = host
    provider.public_key = "pk-test"
    provider.secret_key = SECRET_VALUE
    provider.client = FakeClient(trace)
    return provider


def test_from_env_returns_none_without_credentials(monkeypatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert LangfuseProvider.from_env() is None


def test_from_env_degrades_when_sdk_unavailable(monkeypatch) -> None:
    # Credentials present, but the langfuse SDK import fails: degrade, never raise.
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", SECRET_VALUE)
    monkeypatch.setattr("importlib.import_module", lambda name: (_ for _ in ()).throw(ImportError(name)))
    assert LangfuseProvider.from_env() is None


def test_collect_uses_cost_when_reported() -> None:
    ref = _provider({"total_cost": 0.42, "total_tokens": 1200, "status": "ok"}).collect(
        _cell(), AdapterResult(status=CellStatus.passed, trace_id="trace-1"), Redactor({})
    )
    assert ref is not None
    assert ref.cost.amount == 0.42
    assert ref.cost.source == "langfuse_cost"
    assert ref.external_url == "https://langfuse.example/trace/trace-1"


def test_collect_falls_back_to_tokens_then_unavailable() -> None:
    tokens_only = _provider({"total_tokens": 800}).collect(
        _cell(), AdapterResult(status=CellStatus.passed, trace_id="trace-2"), Redactor({})
    )
    assert tokens_only is not None
    assert tokens_only.cost.amount is None
    assert tokens_only.cost.source == "langfuse_tokens"

    bare = _provider({}, host=None).collect(
        _cell(), AdapterResult(status=CellStatus.passed, trace_id="trace-3"), Redactor({})
    )
    assert bare is not None
    assert bare.cost.source == "unavailable"
    assert bare.external_url is None

    missing = _provider(None).collect(_cell(), AdapterResult(status=CellStatus.passed), Redactor({}))
    assert missing is None


def test_collect_redacts_summary_and_leaks_no_secret() -> None:
    redactor = Redactor({"MICRO_EVAL_SECRET_API_KEY": "leaked-status-secret"})
    ref = _provider({"total_cost": 0.1, "status": "error: leaked-status-secret"}).collect(
        _cell(), AdapterResult(status=CellStatus.passed, trace_id="trace-4"), redactor
    )
    assert ref is not None
    serialized = ref.model_dump_json()
    assert "leaked-status-secret" not in serialized
    assert "[REDACTED:MICRO_EVAL_SECRET_API_KEY]" in serialized
    assert SECRET_VALUE not in serialized
