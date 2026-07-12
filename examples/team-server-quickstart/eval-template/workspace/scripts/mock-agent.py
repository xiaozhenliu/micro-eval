#!/usr/bin/env python3
"""Deterministic mock agent for team server quickstart."""
import sys

output_file = sys.argv[1] if len(sys.argv) > 1 else None

# Read input from stdin (consumed but not used by mock)
task_input = sys.stdin.read()

result = "DONE"

if output_file:
    with open(output_file, "w") as f:
        f.write(result)
else:
    print(result)
