"""Rendering contract tests for the report CLI.

The report is the user's decision surface; a rendering regression directly
misleads conclusions. These tests pin the text/HTML branches with emphasis on
the pass@k column and caveat rendering (and HTML autoescaping).
"""

from __future__ import annotations

from typing import Any

import pytest
from rich.console import Console

import micro_eval.cli.report as report_module
from micro_eval.cli.report import (
    _aggregation_items,
    _format_cost,
    _format_optional_ms,
    _format_optional_rate,
    _format_optional_seconds,
    _format_pass_at_k,
    _print_text_report,
    _render_html_report,
    _stats_rows,
    _template_context,
)


def _sample_data() -> dict[str, Any]:
    return {
        "id": "run-report-fixture",
        "results": [
            {"task_id": "t1", "configuration_id": "baseline", "status": "pass", "score": 1.0, "latency_s": 0.12},
            {"task_id": "t1", "configuration_id": "candidate", "status": "fail", "score": 0.0, "latency_s": 0.34},
        ],
        "artifacts": [],
        "decision": {
            "verdict": "inconclusive",
            "confidence": "low",
            "caveats": ["low_sample", "needs <review>"],
            "aggregation": {
                "per_configuration": {
                    "baseline": {
                        "pass_rate": 2 / 3,
                        "pass_at_k": {"1": 2 / 3, "2": 1.0},
                        "mean_latency_ms": 120.0,
                        "median_latency_ms": 120.0,
                        "total_cost": {"amount": 0.03, "source": "langfuse"},
                    },
                    "candidate": {
                        "pass_rate": 0.0,
                        "pass_at_k": {"1": 0.0},
                        "mean_latency_ms": 340.0,
                        "median_latency_ms": 340.0,
                        "total_cost": {"amount": None, "source": "unavailable"},
                    },
                }
            },
        },
    }


# ---------------------------------------------------------------------------
# Pure formatters
# ---------------------------------------------------------------------------


def test_format_optional_helpers() -> None:
    assert _format_optional_seconds(None) == "-"
    assert _format_optional_seconds(1.5) == "1.50s"
    assert _format_optional_ms(None) == "-"
    assert _format_optional_ms(1500.0) == "1.50s"
    assert _format_optional_rate(None) == "-"
    assert _format_optional_rate(2 / 3) == "67%"


def test_format_pass_at_k_branches() -> None:
    assert _format_pass_at_k(None) == "-"
    assert _format_pass_at_k({}) == "-"
    # A lone @1 is uninformative and collapses to "-".
    assert _format_pass_at_k({"1": 0.5}) == "-"
    assert _format_pass_at_k({"1": 2 / 3, "2": 1.0}) == "@1=67%, @2=100%"


def test_format_cost_branches() -> None:
    assert _format_cost({"total_cost": {"amount": 0.03, "source": "langfuse"}}) == "$0.0300 (langfuse)"
    assert _format_cost({"total_cost": {"amount": None, "source": "unavailable"}}) == "unavailable (unavailable)"
    assert _format_cost({"cost_usd": 1.5}) == "$1.5000"
    assert _format_cost({}) == "-"


# ---------------------------------------------------------------------------
# Aggregation mapping
# ---------------------------------------------------------------------------


def test_aggregation_items_handles_nested_and_flat() -> None:
    nested = {"per_configuration": {"baseline": {"pass_rate": 1.0}}}
    assert _aggregation_items(nested) == [("baseline", {"pass_rate": 1.0})]
    flat = {"baseline": {"pass_rate": 1.0}}
    assert _aggregation_items(flat) == [("baseline", {"pass_rate": 1.0})]


def test_stats_rows_include_pass_at_k_column() -> None:
    rows = _stats_rows(_sample_data()["decision"]["aggregation"])
    by_config = {row["configuration"]: row for row in rows}
    assert by_config["baseline"]["pass_at_k"] == "@1=67%, @2=100%"
    assert by_config["baseline"]["pass_rate"] == "67%"
    assert by_config["baseline"]["cost"] == "$0.0300 (langfuse)"
    assert by_config["candidate"]["pass_at_k"] == "-"
    assert by_config["candidate"]["cost"] == "unavailable (unavailable)"


# ---------------------------------------------------------------------------
# HTML render branch
# ---------------------------------------------------------------------------


def test_render_html_report_pass_at_k_and_caveats() -> None:
    html = _render_html_report(_sample_data())
    assert "run-report-fixture" in html
    # pass@k column rendered.
    assert "@1=67%, @2=100%" in html
    # Caveats rendered as list items.
    assert "low_sample" in html
    # HTML autoescape must neutralise angle brackets in caveat text.
    assert "needs &lt;review&gt;" in html
    assert "<review>" not in html


def test_template_context_exposes_caveats_and_stats() -> None:
    ctx = _template_context(_sample_data())
    assert ctx["run_id"] == "run-report-fixture"
    assert ctx["decision"] == "inconclusive"
    assert "low_sample" in ctx["caveats"]
    assert len(ctx["stats"]) == 2
    assert len(ctx["results"]) == 2


# ---------------------------------------------------------------------------
# Text render branch (rich console capture)
# ---------------------------------------------------------------------------


def test_print_text_report_includes_verdict_caveat_and_pass_at_k(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pin a wide console so rich tables never fold the pass@k cell across lines,
    # which would make the substring assertions environment-dependent.
    wide = Console(width=200)
    monkeypatch.setattr(report_module, "console", wide)
    with wide.capture() as capture:
        _print_text_report(_sample_data())
    out = capture.get()
    assert "run-report-fixture" in out
    assert "inconclusive" in out
    assert "low_sample" in out
    assert "@1=67%" in out


def test_print_text_report_without_decision_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    wide = Console(width=200)
    monkeypatch.setattr(report_module, "console", wide)
    minimal = {"id": "run-empty", "results": []}
    with wide.capture() as capture:
        _print_text_report(minimal)
    assert "run-empty" in capture.get()
