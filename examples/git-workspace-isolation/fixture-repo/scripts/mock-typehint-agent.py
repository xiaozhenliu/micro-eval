#!/usr/bin/env python3
"""Deterministic mock type-hint agent for the git-workspace-isolation example.

This script runs inside an isolated git worktree (the agent CWD is the worktree root).
It reads the task prompt from stdin, annotates app.py with type hints, and prints
the TYPE_HINTS_ADDED completion marker to stdout.

For output_mode: stdout, micro-eval captures this script's stdout as the cell output.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    # Read task prompt from stdin (required by input_mode: stdin).
    prompt = sys.stdin.read()

    # Verify this is a type-hints task.
    if "type" not in prompt.lower():
        print("ERROR: expected a type annotation task prompt", file=sys.stderr)
        return 1

    # The agent CWD is the worktree root — app.py should be here.
    app_path = Path("app.py")
    if not app_path.exists():
        print("ERROR: app.py not found in worktree", file=sys.stderr)
        return 1

    # Write the annotated version.
    app_path.write_text(_annotated_app())

    # Print result summary followed by the required completion marker.
    print("# mock-typehint-agent result")
    print()
    print("Added type annotations to process_sales_data() in app.py.")
    print("All parameters and return type are now annotated.")
    print()
    print("TYPE_HINTS_ADDED")
    return 0


def _annotated_app() -> str:
    """Return a version of app.py with type hints on all functions."""
    return '''\
"""Sales data processing module — with type annotations added.

This is the fixture file after the add-type-hints task runs in an isolated worktree.
"""

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
    # Validate inputs
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

    # Filter records by region
    filtered: list[dict[str, Any]] = []
    for record in records:
        if region_filter is None or record.get("region") == region_filter:
            filtered.append(record)

    # Apply discount
    discounted: list[dict[str, Any]] = []
    for record in filtered:
        price: float = record.get("price", 0.0)
        units: int = record.get("units", 0)
        subtotal: float = price * units
        discounted_subtotal: float = subtotal * (1.0 - discount_rate)
        discounted.append({"record": record, "subtotal": discounted_subtotal})

    # Calculate tax
    taxed: list[dict[str, Any]] = []
    for item in discounted:
        tax_amount: float = item["subtotal"] * tax_rate
        total: float = item["subtotal"] + tax_amount
        taxed.append({
            "record": item["record"],
            "subtotal": item["subtotal"],
            "tax": tax_amount,
            "total": total,
        })

    # Aggregate by product
    aggregated: dict[str, dict[str, Any]] = {}
    for item in taxed:
        product: str = item["record"].get("product", "unknown")
        if product not in aggregated:
            aggregated[product] = {"units": 0, "subtotal": 0.0, "tax": 0.0, "total": 0.0}
        aggregated[product]["units"] += item["record"].get("units", 0)
        aggregated[product]["subtotal"] += item["subtotal"]
        aggregated[product]["tax"] += item["tax"]
        aggregated[product]["total"] += item["total"]

    # Sort by total revenue descending
    sorted_products: list[tuple[str, dict[str, Any]]] = sorted(
        aggregated.items(), key=lambda x: x[1]["total"], reverse=True
    )

    # Build summary report
    report_lines: list[str] = []
    report_lines.append(f"Sales Report | Region: {region_filter or \'all\'} | Currency: {currency}")
    report_lines.append("-" * 60)
    grand_total: float = 0.0
    for product, data in sorted_products:
        line: str = (
            f"{product}: units={data[\'units\']}, "
            f"subtotal={data[\'subtotal\']:.2f}, "
            f"tax={data[\'tax\']:.2f}, "
            f"total={data[\'total\']:.2f} {currency}"
        )
        report_lines.append(line)
        grand_total += data["total"]
    report_lines.append("-" * 60)
    report_lines.append(f"Grand total: {grand_total:.2f} {currency}")

    return {
        "report": "\\n".join(report_lines),
        "grand_total": grand_total,
        "products": dict(sorted_products),
    }
'''


if __name__ == "__main__":
    raise SystemExit(main())
