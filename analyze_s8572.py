#!/usr/bin/env python3
"""Check actual lines for S8572 issues without filtering."""
import json

with open('sonar_issues.json') as f:
    issues = json.load(f)

def get_source_lines(filepath, line_num, context=1):
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        if line_num <= 0 or line_num > len(lines):
            return f"  [line {line_num} out of range, file has {len(lines)} lines]"
        return f"  {line_num}: {lines[line_num-1].rstrip()}"
    except Exception as e:
        return f"  [Error: {e}]"

# S8572 - show actual lines
s8572 = [i for i in issues if i['rule'] == 'python:S8572']
print(f"=== S8572 - First 25 actual lines ===")
count = 0
for i in s8572:
    fp = i['component'].replace('ahmdelbaz28-ux_revit:', '')
    line = i.get('line', 0)
    if line:
        src = get_source_lines(fp, line)
        print(f"{fp}:{line}")
        print(src)
        print()
        count += 1
        if count >= 25:
            break
