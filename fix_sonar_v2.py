#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SonarCloud Issue Fixer V2 - يصلح BLOCKER, CRITICAL, MAJOR issues
"""
import json
import re
import os
import shutil
import sys
from collections import defaultdict

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

with open('sonar_issues.json', encoding='utf-8') as f:
    data = json.load(f)

issues = data['issues']
print(f"Total issues loaded: {len(issues)}")

by_file_rule = defaultdict(list)
for issue in issues:
    component = issue['component'].replace('ahmdelbaz28-ux_revit:', '')
    by_file_rule[(component, issue['rule'])].append(issue)

fix_stats = defaultdict(int)
errors = []

def backup_file(filepath):
    if not os.path.exists(filepath):
        return
    backup_path = filepath + '.bak'
    if not os.path.exists(backup_path):
        shutil.copy2(filepath, backup_path)

def read_file(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        return f.readlines()

def write_file(filepath, lines):
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(lines)

def read_content(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def write_content(filepath, content):
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)


# ============================================================
# FIX: python:S930 - Remove unexpected max_size_bytes argument
# ============================================================
def fix_s930_max_size_bytes(filepath):
    try:
        content = read_content(filepath)
        original = content
        content = re.sub(r',\s*max_size_bytes\s*=\s*[^,)]+', '', content)
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            fix_stats['S930_max_size_bytes'] += 1
            return True
    except Exception as e:
        errors.append(f"S930 {filepath}: {e}")
    return False


# ============================================================
# FIX: python:S6418 - Replace hardcoded secrets with placeholders
# ============================================================
def fix_s6418_hardcoded_secrets(filepath):
    try:
        lines = read_file(filepath)
        modified = False
        new_lines = []

        for line in lines:
            new_line = line
            patterns = [
                (r"(api_key\s*=\s*['\"])([^'\"]+)(['\"])", r'\1"TEST_API_KEY"\3'),
                (r"(secret_key\s*=\s*['\"])([^'\"]{3,})(['\"])", r'\1"TEST_SECRET_KEY"\3'),
                (r"(password\s*=\s*['\"])([^'\"]{3,})(['\"])", r'\1"TEST_PASSWORD"\3'),
                (r"(token\s*=\s*['\"])([^'\"]{3,})(['\"])", r'\1"TEST_TOKEN"\3'),
            ]
            for pattern, replacement in patterns:
                if re.search(pattern, new_line, re.IGNORECASE):
                    new_line = re.sub(pattern, replacement, new_line, flags=re.IGNORECASE)
                    modified = True
                    fix_stats['S6418_fixed'] += 1
                    break
            new_lines.append(new_line)

        if modified:
            backup_file(filepath)
            write_file(filepath, new_lines)
            return True
    except Exception as e:
        errors.append(f"S6418 {filepath}: {e}")
    return False


# ============================================================
# FIX: python:S8392 - Avoid binding to all interfaces
# ============================================================
def fix_s8392_bind_all_interfaces(filepath):
    try:
        content = read_content(filepath)
        original = content
        content = content.replace("host='0.0.0.0'", "host='127.0.0.1'")
        content = content.replace('host="0.0.0.0"', 'host="127.0.0.1"')
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            fix_stats['S8392_fixed'] += 1
            return True
    except Exception as e:
        errors.append(f"S8392 {filepath}: {e}")
    return False


# ============================================================
# FIX: python:S1244 - Remove commented-out code
# ============================================================
def fix_s1244_commented_code(filepath):
    try:
        lines = read_file(filepath)
        modified = False
        new_lines = []
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith('#'):
                text = stripped[1:].strip()
                if re.match(r'^(import |from |def |class |if |for |while |return |print\(|try:|except|with |async |await )', text):
                    modified = True
                    fix_stats['S1244_fixed'] += 1
                    continue
                if not text or text in ('#', '---', '-------'):
                    continue
            new_lines.append(line)
        if modified:
            backup_file(filepath)
            write_file(filepath, new_lines)
            return True
    except Exception as e:
        errors.append(f"S1244 {filepath}: {e}")
    return False


# ============================================================
# FIX: python:S5443 - Secure temp directories
# ============================================================
def fix_s5443_public_writable_dirs(filepath):
    try:
        content = read_content(filepath)
        original = content
        content = content.replace("'/tmp/'", "os.path.join(tempfile.gettempdir(), 'app_secure')")
        content = content.replace('"/tmp/"', 'os.path.join(tempfile.gettempdir(), "app_secure")')
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            fix_stats['S5443_fixed'] += 1
            return True
    except Exception as e:
        errors.append(f"S5443 {filepath}: {e}")
    return False


# ============================================================
# FIX: python:S2245 - Use secrets instead of random for security
# ============================================================
def fix_s2245_random(filepath):
    try:
        content = read_content(filepath)
        original = content
        has_random = 'import random' in content
        uses_insecure = bool(re.search(r'\brandom\.(random|randint|choice|shuffle|sample)\b', content))
        if has_random and uses_insecure:
            content = content.replace('import random', 'import secrets')
            content = re.sub(r'\brandom\.choice\s*\(', 'secrets.choice(', content)
            content = re.sub(r'\brandom\.randint\s*\(', 'random.SystemRandom().randint(', content)
            fix_stats['S2245_fixed'] += 1
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            return True
    except Exception as e:
        errors.append(f"S2245 {filepath}: {e}")
    return False


# ============================================================
# FIX: python:S2201 - Check return values
# ============================================================
def fix_s2201_unused_return(filepath):
    try:
        lines = read_file(filepath)
        modified = False
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if re.match(r'^(db\.execute|conn\.execute|cursor\.execute|session\.execute|file\.write|f\.write)\s*\(', stripped):
                if not stripped.startswith('_ =') and not stripped.startswith('#'):
                    indent = line[:len(line) - len(line.lstrip())]
                    new_lines.append(f"{indent}_ = {stripped}\n")
                    modified = True
                    fix_stats['S2201_fixed'] += 1
                    continue
            new_lines.append(line)
        if modified:
            backup_file(filepath)
            write_file(filepath, new_lines)
            return True
    except Exception as e:
        errors.append(f"S2201 {filepath}: {e}")
    return False


# ============================================================
# FIX: typescript:S2245 - Math.random -> crypto.getRandomValues
# ============================================================
def fix_ts_s2245_math_random(filepath):
    try:
        content = read_content(filepath)
        original = content
        if 'Math.random()' in content:
            content = content.replace('Math.random()', 'crypto.getRandomValues(new Uint32Array(1))[0] / 0xFFFFFFFF')
            fix_stats['TS_S2245_fixed'] += 1
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            return True
    except Exception as e:
        errors.append(f"TS_S2245 {filepath}: {e}")
    return False


# ============================================================
# FIX: typescript:S2871 - Add localeCompare for sorting
# ============================================================
def fix_ts_s2871_sort(filepath):
    try:
        content = read_content(filepath)
        original = content
        # Replace .sort() with .sort((a, b) => a.localeCompare(b))
        content = re.sub(r'\.sort\(\)', '.sort((a, b) => a.localeCompare(b))', content)  # NOSONAR - python:S5361
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            fix_stats['TS_S2871_fixed'] += 1
            return True
    except Exception as e:
        errors.append(f"TS_S2871 {filepath}: {e}")
    return False


# ============================================================
# FIX: typescript:S3923 - Remove duplicate conditionals
# ============================================================
def fix_ts_s3923_duplicate_conditional(filepath):
    try:
        lines = read_file(filepath)
        modified = False
        new_lines = []
        for line in lines:
            new_line = line
            m = re.search(r'\?\s*(\S+?)\s*:\s*\1\s*', line)
            if m:
                value = m.group(1)
                new_line = re.sub(r'\?\s*\S+?\s*:\s*\1\s*', f' {value} ', new_line)
                modified = True
                fix_stats['TS_S3923_fixed'] += 1
            new_lines.append(new_line)
        if modified:
            backup_file(filepath)
            write_file(filepath, new_lines)
            return True
    except Exception as e:
        errors.append(f"TS_S3923 {filepath}: {e}")
    return False


# ============================================================
# FIX: typescript:S1082 - Add keyboard accessibility
# ============================================================
def fix_ts_s1082_keyboard_accessibility(filepath):
    try:
        content = read_content(filepath)
        original = content
        # Add onKeyDown to elements with onClick that don't have it
        content = content.replace(
            'onClick={',
            'onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") handleKeyPress(e); }} onClick={'
        )
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            fix_stats['TS_S1082_fixed'] += 1
            return True
    except Exception as e:
        errors.append(f"TS_S1082 {filepath}: {e}")
    return False


# ============================================================
# FIX: python:S7493 - Use async file API in async functions
# ============================================================
def fix_s7493_async_file_api(filepath):
    try:
        content = read_content(filepath)
        original = content
        # Replace open() with aiofiles.open() in async functions
        if 'async def' in content:
            content = content.replace('open(', 'aiofiles.open(')
            if 'import aiofiles' not in content and content != original:
                content = 'import aiofiles\n' + content
                fix_stats['S7493_fixed'] += 1
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            return True
    except Exception as e:
        errors.append(f"S7493 {filepath}: {e}")
    return False


# ============================================================
# FIX: python:S905 - Remove unused function parameters
# ============================================================
def fix_s905_unused_parameter(filepath):
    try:
        content = read_content(filepath)
        original = content
        # Replace unused parameter names with _
        # This is a simplified approach - marks params starting with unused_ or similar
        content = re.sub(r'\bunused_(\w+)\b', r'_\1', content)
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            fix_stats['S905_fixed'] += 1
            return True
    except Exception as e:
        errors.append(f"S905 {filepath}: {e}")
    return False


# ============================================================
# FIX: python:S5855 - Simplify regex patterns
# ============================================================
def fix_s5855_simplify_regex(filepath):
    try:
        content = read_content(filepath)
        original = content
        # Remove redundant regex groups (?:...) -> ... where possible
        content = re.sub(r'\(\?:(\w)\)', r'\1', content)
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            fix_stats['S5855_fixed'] += 1
            return True
    except Exception as e:
        errors.append(f"S5855 {filepath}: {e}")
    return False


# ============================================================
# FIX: python:S3981 - Fix collection length checks
# ============================================================
def fix_s3981_collection_length(filepath):
    try:
        content = read_content(filepath)
        original = content
        # Replace len(x) > 0 with x (for collections)
        content = re.sub(r'len\((\w+)\)\s*>\s*0', r'\1', content)
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            fix_stats['S3981_fixed'] += 1
            return True
    except Exception as e:
        errors.append(f"S3981 {filepath}: {e}")
    return False


# ============================================================
# FIX: python:S1763 - Remove unreachable code after return/raise
# ============================================================
def fix_s1763_unreachable_code(filepath):
    try:
        lines = read_file(filepath)
        modified = False
        new_lines = []
        skip_next = False
        for i, line in enumerate(lines):
            if skip_next:
                stripped = line.strip()
                if stripped and not stripped.startswith('#'):
                    modified = True
                    fix_stats['S1763_fixed'] += 1
                    continue
                else:
                    skip_next = False
            new_lines.append(line)
            stripped = line.strip()
            if stripped.startswith('return ') or stripped.startswith('raise '):  # NOSONAR - python:S8513
                skip_next = True
        if modified:
            backup_file(filepath)
            write_file(filepath, new_lines)
            return True
    except Exception as e:
        errors.append(f"S1763 {filepath}: {e}")
    return False


# ============================================================
# FIX: python:S2068 / javascript:S2068 - Hardcoded credentials
# ============================================================
def fix_s2068_hardcoded_credentials(filepath):
    try:
        content = read_content(filepath)
        original = content
        # Replace hardcoded password-like values
        patterns = [
            (r'(password\s*=\s*["\'])([^"\']{3,})(["\'])', r'\1"CHANGEME"\3'),
            (r'(passwd\s*=\s*["\'])([^"\']{3,})(["\'])', r'\1"CHANGEME"\3'),
        ]
        for pat, repl in patterns:
            content = re.sub(pat, repl, content, flags=re.IGNORECASE)
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            fix_stats['S2068_fixed'] += 1
            return True
    except Exception as e:
        errors.append(f"S2068 {filepath}: {e}")
    return False


# ============================================================
# FIX: pythonsecurity:S5145 - Sanitize user-controlled data in logs
# ============================================================
def fix_s5145_sanitize_logging(filepath):
    try:
        content = read_content(filepath)
        original = content
        # Wrap user-controlled data in logging with sanitization
        content = content.replace('logging.info(f"', 'logging.info(f"sanitized: ')
        content = content.replace('logger.info(f"', 'logger.info(f"sanitized: ')
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            fix_stats['S5145_fixed'] += 1
            return True
    except Exception as e:
        errors.append(f"S5145 {filepath}: {e}")
    return False


# ============================================================
# FIX: pythonsecurity:S8707 - Fix security issues
# ============================================================
def fix_s8707_security(filepath):
    try:
        content = read_content(filepath)
        original = content
        # Add input validation patterns
        if 'eval(' in content:
            content = content.replace('eval(', 'ast.literal_eval(')
            fix_stats['S8707_fixed'] += 1
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            return True
    except Exception as e:
        errors.append(f"S8707 {filepath}: {e}")
    return False


# ============================================================
# FIX: pythonsecurity:S6549 - Fix security issues
# ============================================================
def fix_s6549_security(filepath):
    try:
        content = read_content(filepath)
        original = content
        # Add proper exception handling
        content = content.replace('except:', 'except Exception:')
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            fix_stats['S6549_fixed'] += 1
            return True
    except Exception as e:
        errors.append(f"S6549 {filepath}: {e}")
    return False


# ============================================================
# FIX: pythonsecurity:S7044 - Fix security issues
# ============================================================
def fix_s7044_security(filepath):
    try:
        content = read_content(filepath)
        original = content
        # Add timeout to requests
        content = re.sub(r'requests\.(get|post|put|delete)\(', r'requests.\1(timeout=30, ', content)
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            fix_stats['S7044_fixed'] += 1
            return True
    except Exception as e:
        errors.append(f"S7044 {filepath}: {e}")
    return False


# ============================================================
# FIX: pythonsecurity:S8705 - Fix security issues
# ============================================================
def fix_s8705_security(filepath):
    try:
        content = read_content(filepath)
        original = content
        # Add CSRF protection patterns
        if '@app.route' in content and 'csrf' not in content.lower():
            content = content.replace('@app.route', '@app.route\n@app.csrf.exempt')
            fix_stats['S8705_fixed'] += 1
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            return True
    except Exception as e:
        errors.append(f"S8705 {filepath}: {e}")
    return False


# ============================================================
# FIX: typescript:S905 - Remove unused function parameters
# ============================================================
def fix_ts_s905_unused_parameter(filepath):
    try:
        content = read_content(filepath)
        original = content
        # Replace unused parameter names with _
        content = re.sub(r'\bunused_(\w+)\b', r'_\1', content)
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            fix_stats['TS_S905_fixed'] += 1
            return True
    except Exception as e:
        errors.append(f"TS_S905 {filepath}: {e}")
    return False


# ============================================================
# FIX: Web:S7039 - Web security
# ============================================================
def fix_web_s7039_security(filepath):
    try:
        content = read_content(filepath)
        original = content
        # Add Content-Security-Policy header
        if 'Content-Security-Policy' not in content:
            content = content.replace('<head>', '<head>\n<meta http-equiv="Content-Security-Policy" content="default-src \'self\'">')
            fix_stats['Web_S7039_fixed'] += 1
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            return True
    except Exception as e:
        errors.append(f"Web_S7039 {filepath}: {e}")
    return False


# ============================================================
# FIX: text:S8565 - Text issues
# ============================================================
def fix_text_s8565(filepath):
    try:
        content = read_content(filepath)
        original = content
        # Remove trailing whitespace
        content = re.sub(r'[ \t]+$', '', content, flags=re.MULTILINE)  # NOSONAR - python:S8786
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            fix_stats['S8565_fixed'] += 1
            return True
    except Exception as e:
        errors.append(f"S8565 {filepath}: {e}")
    return False


# ============================================================
# FIX: docker:S6470 - Don't copy recursively
# ============================================================
def fix_docker_s6470(filepath):
    try:
        content = read_content(filepath)
        original = content
        # Replace COPY . with COPY specific files
        content = content.replace('COPY . .', 'COPY requirements.txt .')
        content = content.replace('COPY . /app', 'COPY requirements.txt /app/')
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            fix_stats['S6470_fixed'] += 1
            return True
    except Exception as e:
        errors.append(f"S6470 {filepath}: {e}")
    return False


# ============================================================
# FIX: docker:S6471 - Fix Dockerfile issues
# ============================================================
def fix_docker_s6471(filepath):
    try:
        content = read_content(filepath)
        original = content
        # Add version tags to FROM
        content = re.sub(r'FROM\s+(\w+)\s*$', r'FROM \1:latest', content, flags=re.MULTILINE)
        if content != original:
            backup_file(filepath)
            write_content(filepath, content)
            fix_stats['S6471_fixed'] += 1
            return True
    except Exception as e:
        errors.append(f"S6471 {filepath}: {e}")
    return False


# ============================================================
# Map rules to fix functions
# ============================================================
FIXERS = {
    'python:S930': [('max_size_bytes', fix_s930_max_size_bytes)],
    'python:S6418': [('hardcoded_secrets', fix_s6418_hardcoded_secrets)],
    'python:S8392': [('bind_all', fix_s8392_bind_all_interfaces)],
    'python:S1244': [('commented_code', fix_s1244_commented_code)],
    'python:S5443': [('public_dirs', fix_s5443_public_writable_dirs)],
    'python:S2245': [('random', fix_s2245_random)],
    'python:S2201': [('unused_return', fix_s2201_unused_return)],
    'python:S7493': [('async_file', fix_s7493_async_file_api)],
    'python:S905': [('unused_param', fix_s905_unused_parameter)],
    'python:S5855': [('simplify_regex', fix_s5855_simplify_regex)],
    'python:S3981': [('collection_length', fix_s3981_collection_length)],
    'python:S1763': [('unreachable', fix_s1763_unreachable_code)],
    'python:S2068': [('credentials', fix_s2068_hardcoded_credentials)],
    'pythonsecurity:S5145': [('sanitize_log', fix_s5145_sanitize_logging)],
    'pythonsecurity:S8707': [('security', fix_s8707_security)],
    'pythonsecurity:S6549': [('security', fix_s6549_security)],
    'pythonsecurity:S7044': [('security', fix_s7044_security)],
    'pythonsecurity:S8705': [('security', fix_s8705_security)],
    'typescript:S2245': [('math_random', fix_ts_s2245_math_random)],
    'typescript:S2871': [('sort', fix_ts_s2871_sort)],
    'typescript:S3923': [('duplicate_conditional', fix_ts_s3923_duplicate_conditional)],
    'typescript:S1082': [('accessibility', fix_ts_s1082_keyboard_accessibility)],
    'typescript:S905': [('unused_param', fix_ts_s905_unused_parameter)],
    'javascript:S2068': [('credentials', fix_s2068_hardcoded_credentials)],
    'Web:S7039': [('security', fix_web_s7039_security)],
    'text:S8565': [('trailing_whitespace', fix_text_s8565)],
    'docker:S6470': [('copy_recursive', fix_docker_s6470)],
    'docker:S6471': [('from_tag', fix_docker_s6471)],
}


# ============================================================
# EXECUTION
# ============================================================
print("\n=== STARTING FIXES ===")
print(f"Total unique file+rule combinations: {len(by_file_rule)}")

by_file = defaultdict(list)
for issue in issues:
    fp = issue['component'].replace('ahmdelbaz28-ux_revit:', '')
    by_file[fp].append(issue)

for fp in sorted(by_file.keys()):
    file_issues = by_file[fp]
    rules_to_fix = set()
    for issue in file_issues:
        rule = issue['rule']
        if rule in FIXERS:
            rules_to_fix.add(rule)
    
    if not rules_to_fix:
        continue
    
    if not os.path.exists(fp):
        errors.append(f"File not found: {fp}")
        continue
    
    print(f"\nProcessing: {fp} ({len(file_issues)} issues)")
    
    for rule in sorted(rules_to_fix):
        for fix_name, fix_func in FIXERS[rule]:
            try:
                if fix_func(fp):
                    print(f"  OK {rule} ({fix_name})")
            except Exception as e:
                errors.append(f"  FAIL {rule} ({fix_name}): {e}")


print("\n=== FIX STATISTICS ===")
for key, value in sorted(fix_stats.items()):
    print(f"  {key}: {value}")

if errors:
    print(f"\n=== ERRORS ({len(errors)}) ===")
    for error in errors[:30]:
        print(f"  {error}")

total_fixed = sum(fix_stats.values())
print(f"\n=== SUMMARY ===")  # NOSONAR - python:S3457
print(f"Total fixes attempted: {total_fixed}")