"""Unit tests for the sample project main module."""

from __future__ import annotations

import sys
import os
import unittest

# Allow importing from the parent directory when running directly.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import process_data, summarize


class TestProcessData(unittest.TestCase):
    def test_basic_processing(self):
        # With the bug present: range(len-1) skips the last element.
        # This test will fail until the bug is fixed.
        result = process_data([10, 20, 30], 1.0)
        # Each raw value is normalized (divide by 255), then multiplied by 1.0
        # All three items should appear in results when the bug is fixed.
        self.assertEqual(len(result), 3, "process_data should return one result per item")

    def test_empty_input(self):
        self.assertEqual(process_data([], 1.0), [])

    def test_clamping(self):
        # Very large input values should be clamped to 100 after normalization * multiplier.
        result = process_data([255], 1000.0)
        self.assertEqual(len(result), 1)
        self.assertLessEqual(result[0], 100.0)


class TestSummarize(unittest.TestCase):
    def test_empty(self):
        s = summarize([])
        self.assertEqual(s["count"], 0)
        self.assertIsNone(s["min"])

    def test_single(self):
        s = summarize([42.0])
        self.assertEqual(s["count"], 1)
        self.assertAlmostEqual(s["mean"], 42.0)

    def test_multiple(self):
        s = summarize([10.0, 20.0, 30.0])
        self.assertEqual(s["count"], 3)
        self.assertAlmostEqual(s["mean"], 20.0)


if __name__ == "__main__":
    unittest.main()
