#!/usr/bin/env python3
"""Refuse a long run unless requested process niceness can be verified."""
import json
import os
import sys

try:
    priority = os.getpriority(os.PRIO_PROCESS, 0)
except OSError as error:
    print(json.dumps({'status': 'blocked', 'operation': 'getpriority', 'error': str(error),
                      'required_niceness': 10}), flush=True)
    sys.exit(2)
if priority < 10:
    print(json.dumps({'status': 'blocked', 'observed_niceness': priority,
                      'required_niceness': 10}), flush=True)
    sys.exit(2)
print(json.dumps({'status': 'PASS', 'observed_niceness': priority,
                  'required_niceness': 10}), flush=True)
