"""Tests for bundled template seeding (GRO-554)."""

from __future__ import annotations

import json

from micro_eval.server.bundled import SEED_MARKER_NAME, seed_bundled_templates
from micro_eval.server.template import TemplateRegistry


def test_seed_on_empty_data_root_creates_both_and_writes_marker(tmp_path):
    """A fresh data root gets both bundled templates and a marker recording them."""
    registry = TemplateRegistry(tmp_path)
    created = seed_bundled_templates(tmp_path, registry)

    assert set(created) == {"demo-codefix", "starter-tasks"}
    ids = {tpl.template_id for tpl in registry.list_templates()}
    assert ids == {"demo-codefix", "starter-tasks"}

    marker_path = tmp_path / SEED_MARKER_NAME
    assert marker_path.exists()
    marker_ids = set(json.loads(marker_path.read_text()))
    assert marker_ids == {"demo-codefix", "starter-tasks"}


def test_deleted_template_is_not_recreated_on_next_seed(tmp_path):
    """Once seeded (and recorded in the marker), a deleted template stays deleted."""
    registry = TemplateRegistry(tmp_path)
    seed_bundled_templates(tmp_path, registry)

    assert registry.delete("starter-tasks")
    assert registry.get("starter-tasks") is None

    created_again = seed_bundled_templates(tmp_path, registry)

    assert created_again == []
    assert registry.get("starter-tasks") is None
    # demo-codefix is untouched by the second call.
    assert registry.get("demo-codefix") is not None


def test_existing_template_without_marker_is_recorded_not_recreated(tmp_path):
    """A template already in the registry (e.g. from an older server) is recorded, not duplicated."""
    registry = TemplateRegistry(tmp_path)
    # Simulate an older data root: demo-codefix was seeded before the marker
    # file existed (e.g. upgrading from a pre-GRO-554 server).
    seed_bundled_templates(tmp_path, registry)
    marker_path = tmp_path / SEED_MARKER_NAME
    marker_path.unlink()
    registry.delete("starter-tasks")

    created = seed_bundled_templates(tmp_path, registry)

    # demo-codefix already existed (no marker) -> recorded, not recreated.
    # starter-tasks was missing and unmarked -> created fresh.
    assert created == ["starter-tasks"]
    ids = {tpl.template_id for tpl in registry.list_templates()}
    assert ids == {"demo-codefix", "starter-tasks"}
    marker_ids = set(json.loads(marker_path.read_text()))
    assert marker_ids == {"demo-codefix", "starter-tasks"}


def test_second_call_is_a_no_op_when_nothing_changed(tmp_path):
    """Calling seed_bundled_templates twice in a row creates nothing new the second time."""
    registry = TemplateRegistry(tmp_path)
    first = seed_bundled_templates(tmp_path, registry)
    assert len(first) == 2

    second = seed_bundled_templates(tmp_path, registry)
    assert second == []
