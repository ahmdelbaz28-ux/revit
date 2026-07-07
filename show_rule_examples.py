#!/usr/bin/env python3
"""Show examples of top SonarCloud rules."""
import json

with open('sonar_issues.json', 'r', encoding='utf-8') as f:
    issues = json.load(f)

# Show examples of top rules
for rule in ['python:S1244', 'python:S3776', 'python:S5778', 'python:S8572', 'python:S125', 'python:S1192', 'python:S8415', 'python:S117', 'python:S1172', 'python:S8410']:
    rule_issues = [i for i in issues if i['rule'] == rule]
    if rule_issues:
        print(f'\n=== {rule} ({len(rule_issues)} issues) ===')
        for i in rule_issues[:3]:
            print(f'  File: {i["component"]}, Line: {i.get("line", "N/A")}')
            print(f'  Message: {i["message"]}')
            print()