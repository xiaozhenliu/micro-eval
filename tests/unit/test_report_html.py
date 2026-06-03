"""Static HTML report safety coverage."""

from micro_eval.cli.report import _render_html_report


def test_html_report_escapes_dynamic_values() -> None:
    html = _render_html_report(
        {
            "id": "run-<script>alert(1)</script>",
            "decision": {
                "verdict": "inconclusive",
                "confidence": "low",
                "caveats": ["<script>alert('caveat')</script>"],
                "aggregation": {},
            },
            "results": [
                {
                    "task_id": "<img src=x onerror=alert(1)>",
                    "configuration_id": "cfg",
                    "status": "pass",
                    "score": 1.0,
                    "latency_s": 0.1,
                }
            ],
            "artifacts": [
                {
                    "artifact_id": "artifact-<script>",
                    "kind": "stdout",
                    "path": "cells/<script>/stdout.txt",
                    "size_bytes": 1,
                    "warning": None,
                }
            ],
        }
    )

    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html
