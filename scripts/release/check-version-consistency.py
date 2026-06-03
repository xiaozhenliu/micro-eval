#!/usr/bin/env python3
"""Compatibility wrapper for the micro-eval release skill."""

from __future__ import annotations

import runpy
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / ".codex" / "skills" / "micro-eval-release" / "scripts" / "check-version-consistency.py"
runpy.run_path(str(SCRIPT), run_name="__main__")
