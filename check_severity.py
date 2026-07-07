#!/usr/bin/env python3
"""Check Blocker and Critical issues."""
import json
from collections import Counter

with open('sonar_issues.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

issues = data['issues']
blockers = [i for i in issues if i['severity'] == 'BLOCKER']
criticals = [i for i in issues if i['severity'] == 'CRITICAL']

print(f'BLOCKER: {len(blockers)}')
for i in blockers:
    print(f'  {i["rule"]}: {i["component"]}:{i.get("line", "?")} - {i["message"][:80]}')

print(f'\nCRITICAL: {len(criticals)}')
crit_rules = Counter(i['rule'] for i in criticals)
for rule, count in crit_rules.most_common(15):
    print(f'  {rule}: {count}')
    ex = next(i for i in criticals if i['rule'] == rule)
    print(f'    Example: {ex["component"]}:{ex.get("line", "?")} - {ex["message"][:80]}')