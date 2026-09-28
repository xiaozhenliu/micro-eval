"""Sales data processing module — ripe for refactoring.

This module intentionally contains a large monolithic function with no type hints,
used as a fixture for the git-workspace-isolation example.
"""


def process_sales_data(records, region_filter, discount_rate, tax_rate, currency):
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
    filtered = []
    for record in records:
        if region_filter is None or record.get("region") == region_filter:
            filtered.append(record)

    # Apply discount
    discounted = []
    for record in filtered:
        price = record.get("price", 0.0)
        units = record.get("units", 0)
        subtotal = price * units
        discounted_subtotal = subtotal * (1.0 - discount_rate)
        discounted.append({"record": record, "subtotal": discounted_subtotal})

    # Calculate tax
    taxed = []
    for item in discounted:
        tax_amount = item["subtotal"] * tax_rate
        total = item["subtotal"] + tax_amount
        taxed.append({"record": item["record"], "subtotal": item["subtotal"], "tax": tax_amount, "total": total})

    # Aggregate by product
    aggregated = {}
    for item in taxed:
        product = item["record"].get("product", "unknown")
        if product not in aggregated:
            aggregated[product] = {"units": 0, "subtotal": 0.0, "tax": 0.0, "total": 0.0}
        aggregated[product]["units"] += item["record"].get("units", 0)
        aggregated[product]["subtotal"] += item["subtotal"]
        aggregated[product]["tax"] += item["tax"]
        aggregated[product]["total"] += item["total"]

    # Sort by total revenue descending
    sorted_products = sorted(aggregated.items(), key=lambda x: x[1]["total"], reverse=True)

    # Build summary report
    report_lines = []
    report_lines.append(f"Sales Report | Region: {region_filter or 'all'} | Currency: {currency}")
    report_lines.append("-" * 60)
    grand_total = 0.0
    for product, data in sorted_products:
        line = (
            f"{product}: units={data['units']}, "
            f"subtotal={data['subtotal']:.2f}, "
            f"tax={data['tax']:.2f}, "
            f"total={data['total']:.2f} {currency}"
        )
        report_lines.append(line)
        grand_total += data["total"]
    report_lines.append("-" * 60)
    report_lines.append(f"Grand total: {grand_total:.2f} {currency}")

    return {
        "report": "\n".join(report_lines),
        "grand_total": grand_total,
        "products": dict(sorted_products),
    }
