from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).parents[2] / "scripts" / "check-work-governance.py"
SPEC = importlib.util.spec_from_file_location("work_governance", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
work_governance = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = work_governance
SPEC.loader.exec_module(work_governance)


def _write_ticket(
    root: Path,
    *,
    identifier: str = "LOCAL-EXAMPLE-01",
    status: str = "ready",
    completion_evidence: bool = False,
) -> Path:
    path = root / ".scratch/example/issues/01-first-ticket.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    evidence = "\n## Completion evidence\n\n- Verification: passed.\n" if completion_evidence else ""
    path.write_text(
        f"# {identifier} — First ticket\n\n"
        f"ID: {identifier}\n"
        "Type: task\n"
        f"Status: {status}\n"
        "Triage: ready-for-agent\n"
        "Executor: agent\n"
        "Blocked by: None\n\n"
        "What to build: do the work.\n"
        f"{evidence}",
        encoding="utf-8",
    )
    return path


def _write_register(root: Path, local_pointer: str) -> None:
    todos = root / "TODOS.md"
    todos.write_text(
        "# Work Register\n\n"
        "## Now\n\n"
        f"- [{local_pointer}](.scratch/example/issues/01-first-ticket.md) — active work.\n\n"
        "## Next\n\n"
        "- [GH-15](https://github.com/xiaozhenliu/micro-eval/issues/15) — upgrade.\n\n"
        "## Waiting\n\n"
        "（无）\n\n"
        "## Roadmap\n\n"
        "- Future option. Trigger: a real need appears.\n\n"
        "## Inbox\n\n"
        "（无）\n",
        encoding="utf-8",
    )


def test_work_register_accepts_ticket_pointer_and_trigger(tmp_path: Path) -> None:
    _write_ticket(tmp_path)
    _write_register(tmp_path, "LOCAL-EXAMPLE-01")
    tickets, ticket_errors = work_governance._read_tickets(tmp_path)

    assert ticket_errors == []
    assert work_governance._check_todos(tmp_path, tickets) == []


def test_work_register_rejects_terminal_ticket_in_active_lane(tmp_path: Path) -> None:
    _write_ticket(tmp_path, status="resolved", completion_evidence=True)
    _write_register(tmp_path, "LOCAL-EXAMPLE-01")
    tickets, ticket_errors = work_governance._read_tickets(tmp_path)

    assert ticket_errors == []
    errors = work_governance._check_todos(tmp_path, tickets)

    assert any("active pointer LOCAL-EXAMPLE-01 targets resolved" in error for error in errors)


def test_ticket_contract_rejects_completed_alias(tmp_path: Path) -> None:
    _write_ticket(tmp_path, status="completed")

    _, errors = work_governance._read_tickets(tmp_path)

    assert any("invalid lifecycle Status 'completed'" in error for error in errors)
