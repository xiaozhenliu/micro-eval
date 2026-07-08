#!/usr/bin/env python3
"""Echo agent for conversational evaluation testing.

Reads JSONL from stdin, responds with echoed content.
"""
import json
import sys

for line in sys.stdin:
    try:
        data = json.loads(line.strip())
        turn = data.get("turn", 0)
        content = data.get("content", "")
        response = {
            "turn": turn,
            "content": f"I received your message: {content}. How can I help further?",
        }
        print(json.dumps(response), flush=True)
    except json.JSONDecodeError:
        pass
