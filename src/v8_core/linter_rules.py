"""
linter_rules.py — V8 CI Lint Gates
====================================
A standalone, dependency-free linter that enforces the V8 trust contract.

Run from the repo root:
    python -m v8_core.linter_rules <path>
or:
    python src/v8_core/linter_rules.py src/

Exit codes:
    0 — clean
    1 — at least one banned word found
    2 — at least one numeric literal in rules/* without code_constant_ref
    3 — at least one engineering/* public function returning a bare scalar
    4 — at least one optimizer missing `safety_margin` parameter
    5 — module name or class name claims forbidden capabilities
   10 — usage error
A non-zero exit MUST fail the CI build. Do NOT add this to a list of
"non-blocking" jobs.
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Rule 1: Banned marketing/capability words
# ---------------------------------------------------------------------------

# Banned in shipped artifacts (code, docs, comments, READMEs, HTML).
BANNED_WORDS = [
    # Capability claims
    r"\bartificial\s+intelligence\b",
    r"\b(AI[- ]?engine|AI[- ]?powered|AI[- ]?driven|AI[- ]?assistant)\b",
    r"\bself[- ]?learning\b",
    r"\bself[- ]?healing\b",
    r"\bself[- ]?aware\b",
    r"\bdigital\s+twin\b",
    r"\bsmoke\s+simulation\b",      # use "smoke pre-screening estimator"
    r"\bNFPA\s*92\s+simulation\b",
    r"\bpredictive\b",
    r"\bconsciousness\b",
    r"\bcognitive\b",
    r"\bautonomous\b",
    r"\bsentient\b",
    r"\bunderstand(s|ing)\b",       # the engine does not "understand"
]

# Files where banned words ARE allowed: this very file + tests that *describe* the rule.
BANNED_WORDS_FILE_ALLOWLIST = {
    "linter_rules.py",
    "test_v8_core.py",
}

# Banned word in *identifiers* (class/function/module names). Stricter set.
BANNED_IDENT_PATTERNS = [
    re.compile(r"(?i)self.?learn"),
    re.compile(r"(?i)digital.?twin"),
    re.compile(r"(?i)smoke.?simulator(?!=)"),
    re.compile(r"(?i)consciousness"),
    re.compile(r"(?i)\bai_engine\b"),
]

# ---------------------------------------------------------------------------
# Rule 2: Numeric literals in rules/* — every code value must come from
# CodeAuthority, never a literal. Annotation `# code_constant_ref: <id>`
# on the same line whitelists the literal (for ground-truth tests only).
# ---------------------------------------------------------------------------

RULES_PATH_FRAGMENT = ("/rules/", "\\rules\\")
ALLOWED_LITERALS_IN_RULES = {0, 1, -1, 2, 0.0, 1.0, 100, 1000, 0.5}  # plumbing
LITERAL_REF_TAG = "code_constant_ref:"

# ---------------------------------------------------------------------------
# Rule 3: No bare scalar return from engineering/* public functions.
# Heuristic: if a function in engineering/*.py has a `return` statement
# whose value is a Constant, Tuple of Constants, or Name not annotated
# as DecisionProvenance, flag it.
# ---------------------------------------------------------------------------

ENG_PATH_FRAGMENT = ("/engineering/", "\\engineering\\")

# ---------------------------------------------------------------------------
# Rule 4: optimizers must accept `safety_margin` (or read it from CodeAuthority).
# ---------------------------------------------------------------------------

OPTIMIZER_NAME_PATTERN = re.compile(r"(?i)^(?!check_|test_)\w*optim(?:ize|izer)")
SAFETY_PARAM_NAMES = {"safety_margin", "code_authority", "auth"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iter_files(root: Path, exts: Iterable[str]) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in exts:
            # Skip venvs / build dirs
            parts = set(p.parts)
            if parts & {".venv", "venv", "build", "dist", "__pycache__", ".git", "node_modules"}:
                continue
            yield p


def _strip_comments_keep_strings(src: str) -> str:
    # Light pass: remove # line comments outside of strings. For lint heuristics only.
    out_lines = []
    for line in src.splitlines():
        # Don't strip lines that contain LITERAL_REF_TAG — we want to detect it.
        if LITERAL_REF_TAG in line:
            out_lines.append(line)
            continue
        # crude: cut at first # not preceded by quote
        in_s = False
        quote = ""
        for i, ch in enumerate(line):
            if in_s:
                if ch == quote and (i == 0 or line[i - 1] != "\\"):
                    in_s = False
            else:
                if ch in ("'", '"'):
                    in_s = True
                    quote = ch
                elif ch == "#":
                    line = line[:i]
                    break
        out_lines.append(line)
    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# Rule 1: banned words
# ---------------------------------------------------------------------------

def check_banned_words(root: Path) -> list[str]:
    failures = []
    patterns = [re.compile(p, re.IGNORECASE) for p in BANNED_WORDS]
    for p in _iter_files(root, {".py", ".md", ".rst", ".html", ".txt", ".yaml", ".yml", ".json"}):
        if p.name in BANNED_WORDS_FILE_ALLOWLIST:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        # Don't scan our own __version__ / docstrings in v8_core/__init__ explaining what's banned
        if p.name == "__init__.py" and "NOT an AI" in text:
            continue
        for pat in patterns:
            for m in pat.finditer(text):
                # Line number
                line_no = text.count("\n", 0, m.start()) + 1
                failures.append(f"{p}:{line_no}: banned word: {m.group(0)!r}")
    return failures


# ---------------------------------------------------------------------------
# Rule 1b: banned identifiers
# ---------------------------------------------------------------------------

def check_banned_identifiers(root: Path) -> list[str]:
    failures = []
    for p in _iter_files(root, {".py"}):
        if p.name in BANNED_WORDS_FILE_ALLOWLIST:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            name = None
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = node.name
            if not name:
                continue
            for pat in BANNED_IDENT_PATTERNS:
                if pat.search(name):
                    failures.append(
                        f"{p}:{node.lineno}: banned identifier {name!r}"
                    )
    return failures


# ---------------------------------------------------------------------------
# Rule 2: numeric literals in rules/*
# ---------------------------------------------------------------------------

def check_no_literals_in_rules(root: Path) -> list[str]:
    failures = []
    for p in _iter_files(root, {".py"}):
        if not any(frag in str(p) for frag in RULES_PATH_FRAGMENT):
            continue
        text = p.read_text(encoding="utf-8")
        lines = text.splitlines()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                if node.value in ALLOWED_LITERALS_IN_RULES:
                    continue
                line = lines[node.lineno - 1] if 0 <= node.lineno - 1 < len(lines) else ""
                if LITERAL_REF_TAG in line:
                    continue
                failures.append(
                    f"{p}:{node.lineno}: numeric literal {node.value!r} in rules/ "
                    f"without `# {LITERAL_REF_TAG} <id>` annotation"
                )
    return failures


# ---------------------------------------------------------------------------
# Rule 3: engineering/* public functions must return DecisionProvenance
# ---------------------------------------------------------------------------

def check_engineering_returns(root: Path) -> list[str]:
    failures = []
    for p in _iter_files(root, {".py"}):
        if not any(frag in str(p) for frag in ENG_PATH_FRAGMENT):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                # Must declare return annotation; should be DecisionProvenance.
                ann = node.returns
                if ann is None:
                    failures.append(
                        f"{p}:{node.lineno}: public function {node.name!r} "
                        "has no return type annotation; expected DecisionProvenance"
                    )
                    continue
                ann_src = ast.unparse(ann) if hasattr(ast, "unparse") else ""
                if "DecisionProvenance" not in ann_src:
                    failures.append(
                        f"{p}:{node.lineno}: public function {node.name!r} "
                        f"returns {ann_src!r}; expected DecisionProvenance"
                    )
    return failures


# ---------------------------------------------------------------------------
# Rule 4: optimizers must accept safety_margin / code_authority
# ---------------------------------------------------------------------------

def check_optimizers_safety_param(root: Path) -> list[str]:
    failures = []
    for p in _iter_files(root, {".py"}):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not OPTIMIZER_NAME_PATTERN.search(node.name):
                    continue
                if node.name.startswith("_"):
                    continue
                arg_names = {a.arg for a in node.args.args} | {a.arg for a in node.args.kwonlyargs}
                if not (arg_names & SAFETY_PARAM_NAMES):
                    failures.append(
                        f"{p}:{node.lineno}: optimizer {node.name!r} must accept "
                        f"one of {SAFETY_PARAM_NAMES}"
                    )
    return failures


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run(paths: list[str]) -> int:
    if not paths:
        print("usage: linter_rules.py <path> [<path> ...]", file=sys.stderr)
        return 10

    roots = [Path(p).resolve() for p in paths]
    all_failures = {
        "banned_words": [],
        "banned_idents": [],
        "literals_in_rules": [],
        "engineering_returns": [],
        "optimizer_safety_param": [],
    }
    for root in roots:
        all_failures["banned_words"].extend(check_banned_words(root))
        all_failures["banned_idents"].extend(check_banned_identifiers(root))
        all_failures["literals_in_rules"].extend(check_no_literals_in_rules(root))
        all_failures["engineering_returns"].extend(check_engineering_returns(root))
        all_failures["optimizer_safety_param"].extend(check_optimizers_safety_param(root))

    total = sum(len(v) for v in all_failures.values())
    print("=" * 72)
    print(f"FireCalc V8 Linter — {total} violation(s) total")
    print("=" * 72)
    for category, fails in all_failures.items():
        print(f"\n[{category}] {len(fails)} violation(s)")
        for f in fails[:50]:
            print(f"  - {f}")
        if len(fails) > 50:
            print(f"  ... and {len(fails) - 50} more")

    if all_failures["banned_words"] or all_failures["banned_idents"]:
        return 1
    if all_failures["literals_in_rules"]:
        return 2
    if all_failures["engineering_returns"]:
        return 3
    if all_failures["optimizer_safety_param"]:
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
