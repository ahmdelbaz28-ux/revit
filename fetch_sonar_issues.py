#!/usr/bin/env python3
"""Fetch all SonarCloud issues for the project."""
import json
import requests
import time

BASE_URL = "https://sonarcloud.io/api/issues/search"
PARAMS = {
    "componentKeys": "ahmdelbaz28-ux_revit",
    "issueStatuses": "OPEN,CONFIRMED",
    "ps": 500,
    "p": 1,
}

all_issues = []
total = None

while True:
    response = requests.get(BASE_URL, params=PARAMS)
    response.raise_for_status()
    data = response.json()
    
    if total is None:
        total = data.get("total", 0)
        print(f"Total issues: {total}")
    
    issues = data.get("issues", [])
    all_issues.extend(issues)
    print(f"Page {PARAMS['p']}: {len(issues)} issues (total so far: {len(all_issues)} / {total})")
    
    if len(all_issues) >= total or len(issues) == 0:
        break
    
    PARAMS["p"] += 1
    time.sleep(0.5)  # Be nice to the API

# Save to file
with open("sonar_issues.json", "w", encoding="utf-8") as f:
    json.dump(all_issues, f, indent=2, ensure_ascii=False)

print(f"Saved {len(all_issues)} issues to sonar_issues.json")