"""Bundled template seeding for a fresh (or upgrading) server data root.

Ships two read-only templates so a new server has something to run
immediately:

- ``demo-codefix`` (pre-existing): deterministic mock agents, zero API cost.
- ``starter-tasks``: five small, self-contained bug-fix tasks with unit
  tests and no configurations (agents are added in the browser).

Seeding is idempotent per template id via a marker file
(``<data_root>/.seeded-templates.json``) so an admin who deletes a bundled
template is not fighting the seeder on every server restart: once a
template id has been seeded (or found already present) it is recorded and
never recreated automatically again.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from micro_eval.server.template import TemplateRegistry

logger = logging.getLogger(__name__)

SEED_MARKER_NAME = ".seeded-templates.json"

# (template_id, source_dir relative to this file's directory, name, description)
BUNDLED_TEMPLATES: tuple[tuple[str, str, str, str], ...] = (
    (
        "demo-codefix",
        "seed_template",
        "Demo: Codefix Showdown (mock agents, free)",
        (
            "Deterministic mock agents for testing the evaluation pipeline. "
            "Zero API cost."
        ),
    ),
    (
        "starter-tasks",
        "seed_templates/starter-tasks",
        "Starter tasks: 5 small codefix problems",
        (
            "Five self-contained bug-fix tasks with unit tests. Add your agent "
            "configurations in the browser and run."
        ),
    ),
)


def _read_marker(marker_path: Path) -> set[str]:
    if not marker_path.exists():
        return set()
    try:
        data = json.loads(marker_path.read_text())
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read seed marker %s; treating as empty", marker_path)
        return set()
    if not isinstance(data, list):
        return set()
    return {str(item) for item in data}


def _write_marker(marker_path: Path, seeded_ids: set[str]) -> None:
    """Write the marker atomically (write to a tmp file, then rename)."""
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(marker_path.parent), prefix=".seeded-templates-", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(sorted(seeded_ids), handle, indent=2)
        os.replace(tmp_name, marker_path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def seed_bundled_templates(data_root: Path, registry: TemplateRegistry) -> list[str]:
    """Create any bundled templates not yet seeded and not already present.

    A template id already recorded in the marker file is always skipped,
    even if it is not currently in the registry (an admin may have deleted
    it on purpose). A template id already in the registry but missing from
    the marker is recorded without being recreated. Only a template id that
    is in neither the marker nor the registry is actually created.

    Returns the list of template ids newly created during this call.
    """
    data_root = Path(data_root)
    marker_path = data_root / SEED_MARKER_NAME
    seeded_ids = _read_marker(marker_path)
    existing_ids = {tpl.template_id for tpl in registry.list_templates()}
    package_root = Path(__file__).resolve().parent

    created: list[str] = []
    changed = False
    for template_id, relative_source, name, description in BUNDLED_TEMPLATES:
        if template_id in seeded_ids:
            continue
        if template_id in existing_ids:
            seeded_ids.add(template_id)
            changed = True
            continue
        source_dir = package_root / relative_source
        if not source_dir.exists():
            logger.warning("Bundled template source missing, skipping: %s", source_dir)
            continue
        try:
            registry.create(
                source_dir=source_dir,
                template_id=template_id,
                name=name,
                description=description,
                author="micro-eval",
            )
        except Exception:
            logger.warning("Could not seed bundled template %s", template_id, exc_info=True)
            continue
        created.append(template_id)
        seeded_ids.add(template_id)
        changed = True

    if changed:
        _write_marker(marker_path, seeded_ids)
    return created
