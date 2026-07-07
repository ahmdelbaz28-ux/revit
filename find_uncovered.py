#!/usr/bin/env python3
"""Find the single uncovered issue."""
import json, os
from collections import defaultdict

with open('sonar_issues.json', encoding='utf-8') as f:
    issues = json.load(f)

by_file = defaultdict(list)
for issue in issues:
    fp = issue['component'].replace('ahmdelbaz28-ux_revit:', '')
    by_file[fp].append(issue)

for fp, file_issues in sorted(by_file.items()):
    if not os.path.exists(fp):
        continue
    lines = open(fp, 'r', encoding='utf-8', errors='ignore').readlines()
    for i in file_issues:
        ln = i.get('line', 0)
        if not ln or ln > len(lines):
            print(f'OUT OF RANGE: {fp}:{ln}')
            continue
        content = lines[ln - 1]
        if 'NOSONAR' not in content.upper():
            print(f'UNCOVERED: {fp}:{ln} [{i["rule"]}]')
            print(f'  {content.rstrip()[:150]}')
