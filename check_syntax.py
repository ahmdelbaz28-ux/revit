#!/usr/bin/env python3
"""Quick syntax check on modified Python files."""
import py_compile
import sys
import os

# Get modified .py files
result = os.popen('git diff --name-only --diff-filter=M').read().strip()
modified_files = [f.strip() for f in result.split('\n') if f.strip().endswith('.py')]

if not modified_files:
    print("No modified Python files to check")
    sys.exit(0)

print(f"Checking {len(modified_files)} modified Python files...")
errors = 0
for f in modified_files:
    if not os.path.exists(f):
        continue
    if '.sonarbak' in f or '.bak' in f:
        continue
    try:
        py_compile.compile(f, doraise=True)
        print(f"  [OK] {f}")
    except py_compile.PyCompileError as e:
        print(f"  [ERROR] {f}: {e}")
        errors += 1

if errors:
    print(f"\nFAILED: {errors} files have syntax errors!")
    sys.exit(1)
else:
    print(f"\nAll {len(modified_files)} files OK!")
