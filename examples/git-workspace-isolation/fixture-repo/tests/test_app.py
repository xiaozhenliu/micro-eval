"""Basic tests for app.py — used as fixture for the git-workspace-isolation example."""

import pytest

from app import process_sales_data

SAMPLE_RECORDS = [
    {"product": "widget", "region": "west", "price": 10.0, "units": 5},
    {"product": "gadget", "region": "east", "price": 20.0, "units": 2},
    {"product": "widget", "region": "east", "price": 10.0, "units": 3},
]


def test_no_filter_returns_all_products():
    result = process_sales_data(SAMPLE_RECORDS, None, 0.0, 0.0, "USD")
    assert "widget" in result["products"]
    assert "gadget" in result["products"]


def test_region_filter():
    result = process_sales_data(SAMPLE_RECORDS, "west", 0.0, 0.0, "USD")
    assert "widget" in result["products"]
    assert "gadget" not in result["products"]


def test_discount_reduces_total():
    result_nodiscount = process_sales_data(SAMPLE_RECORDS, None, 0.0, 0.0, "USD")
    result_discount = process_sales_data(SAMPLE_RECORDS, None, 0.1, 0.0, "USD")
    assert result_discount["grand_total"] < result_nodiscount["grand_total"]


def test_tax_increases_total():
    result_notax = process_sales_data(SAMPLE_RECORDS, None, 0.0, 0.0, "USD")
    result_tax = process_sales_data(SAMPLE_RECORDS, None, 0.0, 0.1, "USD")
    assert result_tax["grand_total"] > result_notax["grand_total"]


def test_report_contains_currency():
    result = process_sales_data(SAMPLE_RECORDS, None, 0.0, 0.0, "EUR")
    assert "EUR" in result["report"]


def test_invalid_records_raises():
    with pytest.raises(ValueError):
        process_sales_data(None, None, 0.0, 0.0, "USD")


def test_invalid_discount_raises():
    with pytest.raises(ValueError):
        process_sales_data(SAMPLE_RECORDS, None, 1.5, 0.0, "USD")
