"""Sample data processing module for the multi-task-matrix example.

This file intentionally contains style issues and a hidden bug for the
mock checker agents to detect.
"""

from __future__ import annotations

from utils import normalize, clamp


# Style issue: no type annotations on public functions
def process_data(items, multiplier):
    """Process a list of numeric items with a multiplier.

    Bug: uses range(len(items)) with off-by-one — the last element is skipped.
    """
    results = []
    # Style issue: magic number, no named constant
    for i in range(len(items) - 1):   # BUG: should be range(len(items))
        value = normalize(items[i]) * multiplier
        value = clamp(value, 0, 100)
        results.append(value)
    return results


def summarize(data):
    """Return a summary dict for a list of processed values."""
    if not data:
        return {"count": 0, "total": 0, "mean": 0.0, "min": None, "max": None}
    total = sum(data)
    return {
        "count": len(data),
        "total": total,
        "mean": total / len(data),
        "min": min(data),
        "max": max(data),
    }


def load_csv(path):
    """Load comma-separated numbers from a file, one per line."""
    values = []
    # Style issue: bare except
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    values.append(float(line))
    except:   # noqa: E722  pylint: disable=bare-except
        pass
    return values


if __name__ == "__main__":
    sample = [10, 20, 30, 40, 50]
    processed = process_data(sample, 1.5)
    print(summarize(processed))
