#!/usr/bin/env python3
"""Analyze S930 (BLOCKER) and other priority issues."""
import json

with open('sonar_issues.json', encoding='utf-8') as f:
    issues = json.load(f)

# S930 - BLOCKER
s930 = [i for i in issues if i['rule'] == 'python:S930']
print(f"=== S930 (BLOCKER): {len(s930)} ===")
for i in s930[:10]:
    fp = i['component'].replace('ahmdelbaz28-ux_revit:', '')
    try:
        with open(fp, encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        line = i.get('line', 0)
        if line and line <= len(lines):
            print(f"  {fp}:{line} -> {lines[line-1].rstrip()[:100]}")
    except Exception as e:
        print(f"  [err {fp}: {e}]")

# S1192 - CRITICAL
s1192 = [i for i in issues if i['rule'] == 'python:S1192']
print(f"\n=== S1192 (CRITICAL): {len(s1192)} sample ===")
for i in s1192[:5]:
    fp = i['component'].replace('ahmdelbaz28-ux_revit:', '')
    try:
        with open(fp, encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        line = i.get('line', 0)
        if line and line <= len(lines):
            print(f"  {fp}:{line} -> {lines[line-1].rstrip()[:90]}")
    except:
        pass

# S1313 - octal
s1313 = [i for i in issues if i['rule'] == 'python:S1313']
print(f"\n=== S1313 (octal): {len(s1313)} sample ===")
for i in s1313[:5]:
    fp = i['component'].replace('ahmdelbaz28-ux_revit:', '')
    try:
        with open(fp, encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        line = i.get('line', 0)
        if line and line <= len(lines):
            print(f"  {fp}:{line} -> {lines[line-1].rstrip()[:90]}")
    except:
        pass
