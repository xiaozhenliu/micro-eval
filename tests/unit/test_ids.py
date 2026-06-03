"""Acceptance tests for canonical ID and digest helpers."""

import re

from micro_eval.models.ids import canonical_digest, new_run_id, safe_path_segment


def test_new_run_id_is_readable_and_collision_resistant():
    first = new_run_id()
    second = new_run_id()
    assert first != second
    assert re.match(r"^run-\d{8}T\d{6}Z-[0-9a-f]{8}$", first)


def test_canonical_digest_is_stable_for_mapping_order():
    left = {"b": 2, "a": [1, 2, 3]}
    right = {"a": [1, 2, 3], "b": 2}
    assert canonical_digest(left) == canonical_digest(right)


def test_safe_path_segment_keeps_cell_separator_and_removes_path_chars():
    assert safe_path_segment("run::task/id::config") == "run::task-id::config"
