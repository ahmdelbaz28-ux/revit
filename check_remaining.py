#!/usr/bin/env python3
"""Check remaining issues in targeted files."""
import json, os

with open('sonar_issues.json', encoding='utf-8') as f:
    issues = json.load(f)

files_to_check = [
    'frontend/src/components/mockups/engineering/CableCalculator.tsx',
    'frontend/src/components/mockups/engineering/PythonSwagger.tsx',
    'skills/pdf/scripts/setup.sh',
    'frontend/src/components/mockups/engineering/ReportGenerator.tsx',
    '.github/workflows/deploy.yml',
]

for fp in files_to_check:
    if not os.path.exists(fp):
        print(f'[MISSING] {fp}')
        continue
    lines = open(fp, 'r', encoding='utf-8', errors='ignore').readlines()
    file_issues = [i for i in issues if i['component'].replace('ahmdelbaz28-ux_revit:', '') == fp]
    has_nosonar = sum(1 for l in lines if 'NOSONAR' in l.upper())
    print(f'{fp}: {len(file_issues)} issues, {has_nosonar} lines with NOSONAR')
    for i in file_issues[:3]:
        ln = i.get('line', 0)
        if ln and ln <= len(lines):
            print(f'  Line {ln}: {lines[ln-1].rstrip()[:120]}')
    print()
