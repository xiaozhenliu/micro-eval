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
        "# 未完成工作总目录\n\n"
        "## 当前执行（Now）\n\n"
        f"- [{local_pointer}](.scratch/example/issues/01-first-ticket.md) — active work.\n\n"
        "## 下一步（Next）\n\n"
        "- [GH-15](https://github.com/xiaozhenliu/micro-eval/issues/15) — 升级。\n\n"
        "## 等待解除（Waiting）\n\n"
        "（无）\n\n"
        "## 路线图（Roadmap）\n\n"
        "- Future option. 规划状态：路线图（未阻塞）。触发/晋升时机：a real need appears.\n\n"
        "## 收件箱（Inbox）\n\n"
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


def _archive_ticket(root: Path, identifier: str = "LOCAL-EXAMPLE-01") -> Path:
    source = root / ".scratch/example/issues/01-first-ticket.md"
    target = root / ".scratch/example/issues/resolved/01-first-ticket.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    source.replace(target)
    return target


def test_archived_ticket_keeps_id_outside_active_scan(tmp_path: Path) -> None:
    _write_ticket(tmp_path, status="resolved", completion_evidence=True)
    _archive_ticket(tmp_path)
    tickets, ticket_errors = work_governance._read_tickets(tmp_path)

    assert ticket_errors == []
    assert tickets == []
    assert work_governance._check_archived_tickets(tmp_path, tickets) == []


def test_archived_ticket_rejects_duplicate_of_active_id(tmp_path: Path) -> None:
    _write_ticket(tmp_path, status="resolved", completion_evidence=True)
    _archive_ticket(tmp_path)
    _write_ticket(tmp_path, status="ready")
    tickets, ticket_errors = work_governance._read_tickets(tmp_path)

    assert ticket_errors == []
    assert [ticket.identifier for ticket in tickets] == ["LOCAL-EXAMPLE-01"]
    errors = work_governance._check_archived_tickets(tmp_path, tickets)

    assert any(
        "archived ID LOCAL-EXAMPLE-01 duplicates an active ticket" in error
        for error in errors
    )
