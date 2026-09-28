#!/usr/bin/env python3
"""Count core source lines while excluding tests and documentation."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CORE_ROOTS = (Path("src/micro_eval"), Path("ui/src"))
LANGUAGES = {
    ".css": "CSS",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
}
EXCLUDED_DIRECTORIES = {
    "__tests__",
    "docs",
    "documentation",
    "test",
    "tests",
}


@dataclass
class LineCount:
    files: int = 0
    non_blank: int = 0
    physical: int = 0

    def add(self, lines: list[str]) -> None:
        self.files += 1
        self.non_blank += sum(bool(line.strip()) for line in lines)
        self.physical += len(lines)


def is_test_file(path: Path) -> bool:
    """Return whether a source filename follows a common test convention."""
    stem = path.stem.casefold()
    return (
        stem.startswith("test_")
        or stem.endswith("_test")
        or stem.endswith(".test")
        or stem.endswith(".spec")
    )


def iter_core_files() -> Iterable[tuple[Path, Path]]:
    """Yield (configured root, source file) pairs in stable path order."""
    for relative_root in CORE_ROOTS:
        source_root = REPOSITORY_ROOT / relative_root
        if not source_root.is_dir():
            continue
        for path in sorted(source_root.rglob("*")):
            relative_path = path.relative_to(source_root)
            if (
                not path.is_file()
                or path.is_symlink()
                or path.suffix.casefold() not in LANGUAGES
                or any(part.casefold() in EXCLUDED_DIRECTORIES for part in relative_path.parts)
                or is_test_file(path)
            ):
                continue
            yield relative_root, path


def collect_counts() -> tuple[dict[str, LineCount], dict[str, LineCount]]:
    """Collect counts grouped by configured root and source language."""
    by_root: defaultdict[str, LineCount] = defaultdict(LineCount)
    by_language: defaultdict[str, LineCount] = defaultdict(LineCount)

    for relative_root, path in iter_core_files():
        lines = path.read_text(encoding="utf-8").splitlines()
        by_root[relative_root.as_posix()].add(lines)
        by_language[LANGUAGES[path.suffix.casefold()]].add(lines)

    return dict(by_root), dict(by_language)


def total_count(groups: dict[str, LineCount]) -> LineCount:
    """Sum a set of disjoint groups."""
    return LineCount(
        files=sum(count.files for count in groups.values()),
        non_blank=sum(count.non_blank for count in groups.values()),
        physical=sum(count.physical for count in groups.values()),
    )


def print_table(title: str, groups: dict[str, LineCount]) -> None:
    label_width = max((len(label) for label in groups), default=4)
    label_width = max(label_width, 4)
    print(title)
    print(f"{'Group':<{label_width}}  {'Files':>7}  {'Non-blank':>10}  {'Physical':>10}")
    print(f"{'-' * label_width}  {'-' * 7}  {'-' * 10}  {'-' * 10}")
    for label, count in sorted(groups.items()):
        print(
            f"{label:<{label_width}}  {count.files:>7,}  "
            f"{count.non_blank:>10,}  {count.physical:>10,}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Count core source files under src/micro_eval and ui/src, excluding "
            "tests and documentation. Non-blank counts include comment lines."
        )
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    by_root, by_language = collect_counts()
    total = total_count(by_root)

    if args.json:
        print(
            json.dumps(
                {
                    "roots": {label: asdict(count) for label, count in sorted(by_root.items())},
                    "languages": {
                        label: asdict(count) for label, count in sorted(by_language.items())
                    },
                    "total": asdict(total),
                },
                indent=2,
            )
        )
        return 0

    print_table("By source root", by_root)
    print()
    print_table("By language", by_language)
    print()
    print(
        f"TOTAL: {total.files:,} files, {total.non_blank:,} non-blank lines, "
        f"{total.physical:,} physical lines"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
