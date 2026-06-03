"""Tests for the ledger allocation example."""

from __future__ import annotations

import unittest

from ledger import split_amount_cents


class SplitAmountCentsTests(unittest.TestCase):
    def test_preserves_total_when_remainder_exists(self) -> None:
        shares = split_amount_cents(100, [1, 1, 1])
        self.assertEqual(sum(shares), 100)
        self.assertEqual(shares, [34, 33, 33])

    def test_distributes_larger_fractional_remainders_first(self) -> None:
        shares = split_amount_cents(101, [1, 2, 3])
        self.assertEqual(sum(shares), 101)
        self.assertEqual(shares, [17, 34, 50])

    def test_rejects_invalid_inputs(self) -> None:
        with self.assertRaises(ValueError):
            split_amount_cents(-1, [1])
        with self.assertRaises(ValueError):
            split_amount_cents(10, [])
        with self.assertRaises(ValueError):
            split_amount_cents(10, [1, 0])


if __name__ == "__main__":
    unittest.main()
