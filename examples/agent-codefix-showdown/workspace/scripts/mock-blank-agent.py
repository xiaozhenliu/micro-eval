#!/usr/bin/env python3
"""Mock agent that reads input from a file (input_mode: file)."""
import sys

# In file input mode, argv[1] is the input file, argv[2] is the output file
input_file = sys.argv[1] if len(sys.argv) > 1 else None
output_file = sys.argv[2] if len(sys.argv) > 2 else None

if input_file:
    with open(input_file) as f:
        task_input = f.read()
else:
    task_input = sys.stdin.read()

result = '''def fibonacci(n):
    """Return the nth Fibonacci number (0-indexed)."""
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b
'''

if output_file:
    with open(output_file, "w") as f:
        f.write(result)
else:
    print(result)
