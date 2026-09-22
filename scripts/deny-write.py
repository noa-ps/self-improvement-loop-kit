#!/usr/bin/env python3
"""Claude PreToolUse helper: exit 2 if the write target is sealed."""

import json
import sys

blocked = sys.argv[1:]
data = json.load(sys.stdin)
path = str((data.get("tool_input") or {}).get("file_path") or "")
if any(b and b in path for b in blocked):
    sys.exit(2)
sys.exit(0)
