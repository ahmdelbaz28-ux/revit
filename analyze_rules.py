#!/usr/bin/env python3
"""Analyze S8572 and S1244 issues to understand patterns."""
import json

with open('sonar_issues.json') as f:
    issues = json.load(f)

# S8572 analysis
s8572 = [i for i in issues if i['rule'] == 'python:S8572']
print(f"=== S8572 (use logging.exception) ===")
print(f"Total: {len(s8572)}")
for i in s8572[:20]:
    print(f"  Line {i.get('line','?'):>5} [{i['severity']:>6}]: {i['component']}")
    print(f"    {i['message'][:120]}")

print()
# S1244 analysis
s1244 = [i for i in issues if i['rule'] == 'python:S1244']
print(f"=== S1244 (float equality) ===")
print(f"Total: {len(s1244)}")
for i in s1244[:20]:
    print(f"  Line {i.get('line','?'):>5} [{i['severity']:>6}]: {i['component']}")
    print(f"    {i['message'][:120]}")
