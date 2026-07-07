#!/usr/bin/env python3
"""Find pyproject.toml file-level issue."""
import json
with open('sonar_issues.json', encoding='utf-8') as f:
    issues = json.load(f)
for i in issues:
    if 'pyproject.toml' in i['component']:
        print(f"rule: {i['rule']}, line: {i.get('line','?')}, msg: {i['message'][:200]}")
        print(f"component: {i['component']}")
