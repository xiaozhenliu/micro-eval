#!/usr/bin/env python3
"""Deterministic mock refactoring agent for the git-workspace-isolation example.

This script runs inside an isolated git worktree (the agent CWD is the worktree root).
It reads the task prompt from stdin, pretends to refactor app.py, and prints
the REFACTOR_COMPLETE completion marker to stdout.

For output_mode: stdout, micro-eval captures this script's stdout as the cell output.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    # Read task prompt from stdin (required by input_mode: stdin).
    prompt = sys.stdin.read()
    prompt_lower = prompt.lower()

    # Detect task type from prompt content and dispatch accordingly.
    if "type" in prompt_lower and "hint" in prompt_lower:
        return _run_typehint_task()
    if "refactor" in prompt_lower:
        return _run_refactor_task()

    print("ERROR: unrecognised task prompt (expected 'refactor' or 'type hint')", file=sys.stderr)
    return 1


def _run_refactor_task() -> int:
    # The agent CWD is the worktree root — app.py should be here.
    app_path = Path("app.py")
    if not app_path.exists():
        print("ERROR: app.py not found in worktree", file=sys.stderr)
        return 1

    original = app_path.read_text()

    # Deterministic mock refactoring: add helper function stubs at the top.
    refactored = _mock_refactor(original)
    app_path.write_text(refactored)

    # Print result summary followed by the required completion marker.
    print("# mock-refactor-agent result")
    print()
    print("Refactored app.py: extracted validate_inputs, filter_by_region,")
    print("apply_discount, apply_tax, aggregate_by_product, build_report")
    print("as separate helper functions.")
    print()
    print("REFACTOR_COMPLETE")
    return 0


def _run_typehint_task() -> int:
    # The agent CWD is the worktree root — app.py should be here.
    app_path = Path("app.py")
    if not app_path.exists():
        print("ERROR: app.py not found in worktree", file=sys.stderr)
        return 1

    app_path.write_text(_annotated_app())

    print("# mock-refactor-agent (type-hint mode) result")
    print()
    print("Added type annotations to process_sales_data() in app.py.")
    print("All parameters and return type are now annotated.")
    print()
    print("TYPE_HINTS_ADDED")
    return 0


def _mock_refactor(original: str) -> str:
    """Produce a deterministically refactored version of the source."""
    header = '''\
"""Sales data processing module — refactored.

Helper functions extracted from process_sales_data for clarity and testability.
"""
from __future__ import annotations


def _validate_inputs(records, discount_rate, tax_rate):
    """Validate processing inputs."""
    if records is None:
        raise ValueError("records cannot be None")
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    if not 0.0 <= discount_rate <= 1.0:
        raise ValueError("discount_rate must be between 0.0 and 1.0")
    if not 0.0 <= tax_rate <= 1.0:
        raise ValueError("tax_rate must be between 0.0 and 1.0")


def _filter_by_region(records, region_filter):
    """Return only records matching the given region (or all if None)."""
    if region_filter is None:
        return list(records)
    return [r for r in records if r.get("region") == region_filter]


def _apply_discount(records, discount_rate):
    """Return list of (record, subtotal) pairs after discount."""
    result = []
    for r in records:
        subtotal = r.get("price", 0.0) * r.get("units", 0) * (1.0 - discount_rate)
        result.append({"record": r, "subtotal": subtotal})
    return result


def _apply_tax(discounted, tax_rate):
    """Return list of (record, subtotal, tax, total) items."""
    result = []
    for item in discounted:
        tax = item["subtotal"] * tax_rate
        total = item["subtotal"] + tax
        result.append({"record": item["record"], "subtotal": item["subtotal"],
                        "tax": tax, "total": total})
    return result


def _aggregate_by_product(taxed):
    """Sum units, subtotal, tax, and total per product."""
    agg = {}
    for item in taxed:
        product = item["record"].get("product", "unknown")
        if product not in agg:
            agg[product] = {"units": 0, "subtotal": 0.0, "tax": 0.0, "total": 0.0}
        agg[product]["units"] += item["record"].get("units", 0)
        agg[product]["subtotal"] += item["subtotal"]
        agg[product]["tax"] += item["tax"]
        agg[product]["total"] += item["total"]
    return agg


def _build_report(sorted_products, region_filter, currency):
    """Render a text summary report."""
    lines = [
        f"Sales Report | Region: {region_filter or 'all'} | Currency: {currency}",
        "-" * 60,
    ]
    grand_total = 0.0
    for product, data in sorted_products:
        lines.append(
            f"{product}: units={data['units']}, subtotal={data['subtotal']:.2f}, "
            f"tax={data['tax']:.2f}, total={data['total']:.2f} {currency}"
        )
        grand_total += data["total"]
    lines += ["-" * 60, f"Grand total: {grand_total:.2f} {currency}"]
    return "\\n".join(lines), grand_total


'''

    main_fn = '''
def process_sales_data(records, region_filter, discount_rate, tax_rate, currency):
    """Process sales data: filter, discount, tax, aggregate, report."""
    _validate_inputs(records, discount_rate, tax_rate)
    if region_filter is not None and not isinstance(region_filter, str):
        raise ValueError("region_filter must be a string or None")
    filtered = _filter_by_region(records, region_filter)
    discounted = _apply_discount(filtered, discount_rate)
    taxed = _apply_tax(discounted, tax_rate)
    aggregated = _aggregate_by_product(taxed)
    sorted_products = sorted(aggregated.items(), key=lambda x: x[1]["total"], reverse=True)
    report, grand_total = _build_report(sorted_products, region_filter, currency)
    return {"report": report, "grand_total": grand_total, "products": dict(sorted_products)}
'''
    return header + main_fn


def _annotated_app() -> str:
    """Return a version of app.py with type hints on all functions."""
    return '''\
"""Sales data processing module — with type annotations added."""

from __future__ import annotations

from typing import Any


def process_sales_data(
    records: list[dict[str, Any]],
    region_filter: str | None,
    discount_rate: float,
    tax_rate: float,
    currency: str,
) -> dict[str, Any]:
    """Process sales records: filter by region, apply discount and tax, aggregate."""
    if records is None:
        raise ValueError("records cannot be None")
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    if region_filter is not None and not isinstance(region_filter, str):
        raise ValueError("region_filter must be a string or None")
    if not 0.0 <= discount_rate <= 1.0:
        raise ValueError("discount_rate must be between 0.0 and 1.0")
    if not 0.0 <= tax_rate <= 1.0:
        raise ValueError("tax_rate must be between 0.0 and 1.0")

    filtered: list[dict[str, Any]] = [
        r for r in records
        if region_filter is None or r.get("region") == region_filter
    ]
    discounted: list[dict[str, Any]] = [
        {"record": r, "subtotal": r.get("price", 0.0) * r.get("units", 0) * (1.0 - discount_rate)}
        for r in filtered
    ]
    taxed: list[dict[str, Any]] = [
        {"record": i["record"], "subtotal": i["subtotal"],
         "tax": i["subtotal"] * tax_rate, "total": i["subtotal"] * (1.0 + tax_rate)}
        for i in discounted
    ]
    aggregated: dict[str, dict[str, Any]] = {}
    for item in taxed:
        product: str = item["record"].get("product", "unknown")
        if product not in aggregated:
            aggregated[product] = {"units": 0, "subtotal": 0.0, "tax": 0.0, "total": 0.0}
        aggregated[product]["units"] += item["record"].get("units", 0)
        aggregated[product]["subtotal"] += item["subtotal"]
        aggregated[product]["tax"] += item["tax"]
        aggregated[product]["total"] += item["total"]
    sorted_products = sorted(aggregated.items(), key=lambda x: x[1]["total"], reverse=True)
    lines: list[str] = [
        f"Sales Report | Region: {region_filter or 'all'} | Currency: {currency}",
        "-" * 60,
    ]
    grand_total: float = 0.0
    for product, data in sorted_products:
        lines.append(
            f"{product}: units={data['units']}, subtotal={data['subtotal']:.2f}, "
            f"tax={data['tax']:.2f}, total={data['total']:.2f} {currency}"
        )
        grand_total += data["total"]
    lines += ["-" * 60, f"Grand total: {grand_total:.2f} {currency}"]
    return {
        "report": "\\n".join(lines),
        "grand_total": grand_total,
        "products": dict(sorted_products),
    }
'''


if __name__ == "__main__":
    raise SystemExit(main())
