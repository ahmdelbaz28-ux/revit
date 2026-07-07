#!/usr/bin/env python3
"""Analyze actual source lines for S8572 and S1244 issues."""
import json

with open('sonar_issues.json') as f:
    issues = json.load(f)

def get_source_lines(filepath, line_num, context=3):
    """Extract lines around the issue from the actual source file."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        start = max(0, line_num - context - 1)
        end = min(len(lines), line_num + context)
        result = []
        for i in range(start, end):
            marker = ">>>" if i == line_num - 1 else "   "
            result.append(f"  {marker} {i+1}: {lines[i].rstrip()}")
        return '\n'.join(result)
    except Exception as e:
        return f"  [Error: {e}]"

# S8572 - check actual patterns
s8572 = [i for i in issues if i['rule'] == 'python:S8572']
print(f"=== S8572 Sample Patterns ===")
count = 0
for i in s8572:
    fp = i['component'].replace('ahmdelbaz28-ux_revit:', '')
    line = i.get('line', 0)
    if line:
        src = get_source_lines(fp, line, 2)
        if 'logger.error' in src or 'logging.error' in src:
            print(f"\n--- {fp}:{line} ---")
            print(src)
            count += 1
            if count >= 10:
                break

print()
# S1244 - check actual patterns
s1244 = [i for i in issues if i['rule'] == 'python:S1244']
print(f"=== S1244 Sample Patterns ===")
count = 0
for i in s1244[:20]:
    fp = i['component'].replace('ahmdelbaz28-ux_revit:', '')
    line = i.get('line', 0)
    if line:
        src = get_source_lines(fp, line, 2)
        print(f"\n--- {fp}:{line} ---")
        print(src)
        count += 1
        if count >= 10:
            break

print()
# Also show files that have the most S8572 issues
from collections import Counter
s8572_by_file = Counter()
for i in s8572:
    fp = i['component'].replace('ahmdelbaz28-ux_revit:', '')
    s8572_by_file[fp] += 1
print(f"\n=== Top files by S8572 count ===")
for fp, cnt in s8572_by_file.most_common(10):
    print(f"  {cnt:>3}: {fp}")
