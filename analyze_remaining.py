#!/usr/bin/env python3
"""Analyze remaining issues after V204 + batch 1."""
import json
from collections import Counter

with open('sonar_issues.json', encoding='utf-8') as f:
    issues = json.load(f)

print(f"Total remaining issues: {len(issues)}")

# By rule
rule_counts = Counter()
severity_counts = Counter()
for i in issues:
    rule_counts[i['rule']] += 1
    severity_counts[i['severity']] += 1

print(f"\n=== By Severity ===")
for s, c in severity_counts.most_common():
    print(f"  {s:>8}: {c}")

print(f"\n=== Top 20 Rules ===")
for (rule, count) in rule_counts.most_common(20):
    severity = next((i['severity'] for i in issues if i['rule'] == rule), '')
    print(f"  {count:>5}: {rule} [{severity}]")

# Check S8572 specifically
s8572 = [i for i in issues if i['rule'] == 'python:S8572']
print(f"\n=== S8572 remaining: {len(s8572)} ===")
for i in s8572[:5]:
    fp = i['component'].replace('ahmdelbaz28-ux_revit:', '')
    try:
        with open(fp) as f:
            lines = f.readlines()
        line = i.get('line', 0)
        if line and line <= len(lines):
            print(f"  {fp}:{line} -> {lines[line-1].rstrip()}")
    except:
        pass
