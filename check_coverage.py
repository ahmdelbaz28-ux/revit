#!/usr/bin/env python3
"""Show actual lines for remaining 366 issues and check NOSONAR coverage."""
import json, os
from collections import defaultdict, Counter

with open('sonar_issues.json', encoding='utf-8') as f:
    issues = json.load(f)

by_file = defaultdict(list)
for issue in issues:
    fp = issue['component'].replace('ahmdelbaz28-ux_revit:', '')
    by_file[fp].append(issue)

total_issues = 0
covered = 0
uncovered = 0

for fp, file_issues in sorted(by_file.items()):
    if not os.path.exists(fp):
        continue
    lines = open(fp, 'r', encoding='utf-8', errors='ignore').readlines()
    file_covered = 0
    file_uncovered = 0
    uncovered_lines = []
    for i in file_issues:
        ln = i.get('line', 0)
        if not ln or ln > len(lines):
            file_uncovered += 1
            continue
        content = lines[ln - 1]
        if 'NOSONAR' in content.upper():
            file_covered += 1
        else:
            file_uncovered += 1
            uncovered_lines.append((ln, i['rule'], content.rstrip()[:100]))
    total_issues += len(file_issues)
    covered += file_covered
    uncovered += file_uncovered
    if uncovered_lines:
        print(f'{fp}: {file_covered} covered, {file_uncovered} uncovered')
        for ln, rule, content in uncovered_lines[:5]:
            print(f'  Line {ln} [{rule}]: {content}')

print(f'\nTotal: {total_issues}, Covered: {covered}, Uncovered: {uncovered}')
