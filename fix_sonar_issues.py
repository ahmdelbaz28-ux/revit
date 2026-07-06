#!/usr/bin/env python3
"""
Automatic SonarCloud Issue Fixer
Fixes common issues in bulk where possible
"""

import json
import re
import os
from pathlib import Path
from collections import defaultdict

# Load issues
with open('sonar_issues.json') as f:
    data = json.load(f)

issues = data['issues']
print(f"Total issues to fix: {len(issues)}")

# Group by rule
by_rule = defaultdict(list)
for issue in issues:
    by_rule[issue['rule']].append(issue)

print("\n=== ISSUE BREAKDOWN ===")
for rule, rule_issues in sorted(by_rule.items(), key=lambda x: -len(x[1])):
    print(f"{rule}: {len(rule_issues)} issues")

# Strategy: Fix rules that can be automated
AUTOMATABLE_RULES = {
    'python:S1244': 'Remove commented-out code and replace TODOs with actionable tickets',
    'python:S6418': 'Replace hardcoded secrets with environment variables',
    'python:S2245': 'Replace random with secrets module for security-sensitive contexts',
    'python:S930': 'Remove unexpected named arguments',
    'typescript:S1082': 'Add keyboard accessibility to clickable elements',
    'typescript:S2245': 'Replace Math.random with crypto.getRandomValues',
    'typescript:S3923': 'Fix redundant conditionals',
    'python:S5443': 'Replace insecure random with secrets',
    'python:S5332': 'Use secure cryptographic methods',
    'pythonsecurity:S5145': 'Sanitize logs',
}

print("\n=== AUTOMATABLE RULES ===")
for rule in AUTOMATABLE_RULES:
    if rule in by_rule:
        print(f"  {rule}: {len(by_rule[rule])} issues - {AUTOMATABLE_RULES[rule]}")

print("\n=== MANUAL FIX REQUIRED ===")
for rule in by_rule:
    if rule not in AUTOMATABLE_RULES:
        print(f"  {rule}: {len(by_rule[rule])} issues")

# Generate fix report
fix_report = {
    'total_issues': len(issues),
    'automatable': sum(len(by_rule[r]) for r in AUTOMATABLE_RULES if r in by_rule),
    'manual': sum(len(by_rule[r]) for r in by_rule if r not in AUTOMATABLE_RULES),
    'by_rule': {r: len(i) for r, i in by_rule.items()}
}

with open('sonar_fix_plan.json', 'w') as f:
    json.dump(fix_report, f, indent=2)

print("\nFix plan saved to sonar_fix_plan.json")