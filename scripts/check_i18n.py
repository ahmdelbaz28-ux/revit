#!/usr/bin/env python3
"""
i18n completeness checker.
Fails if en.json keys are missing from ar.json (or any other locale).

Usage:
    python scripts/check_i18n.py
    # Exit code 0 = all locales complete
    # Exit code 1 = missing keys found
"""

import json
import sys
from pathlib import Path

LOCALES_DIR = Path(__file__).parent.parent / "frontend" / "src" / "i18n" / "locales"
REFERENCE_LOCALE = "en"
TARGET_LOCALES = ["ar"]  # Add more as they become available


def get_all_keys(obj: dict, prefix: str = "") -> list[str]:
    """Recursively get all leaf keys from a nested dict."""
    keys = []
    for key, val in obj.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(val, dict):
            keys.extend(get_all_keys(val, full_key))
        else:
            keys.append(full_key)
    return keys


def check_locale(reference: dict, target: dict, target_name: str) -> list[str]:
    """Return list of missing keys in target."""
    ref_keys = set(get_all_keys(reference))
    tgt_keys = set(get_all_keys(target))
    return sorted(ref_keys - tgt_keys)


def main() -> int:
    ref_path = LOCALES_DIR / f"{REFERENCE_LOCALE}.json"
    if not ref_path.exists():
        print(f"ERROR: Reference locale not found: {ref_path}")
        return 1

    reference = json.loads(ref_path.read_text(encoding="utf-8"))
    ref_count = len(get_all_keys(reference))

    all_good = True
    for locale in TARGET_LOCALES:
        target_path = LOCALES_DIR / f"{locale}.json"
        if not target_path.exists():
            print(f"ERROR: Locale file not found: {target_path}")
            all_good = False
            continue

        target = json.loads(target_path.read_text(encoding="utf-8"))
        missing = check_locale(reference, target, locale)

        if missing:
            print(f"\nFAIL {locale}.json: {len(missing)} missing keys (out of {ref_count} total)")
            for key in missing[:20]:
                print(f"   - {key}")
            if len(missing) > 20:
                print(f"   ... and {len(missing) - 20} more")
            all_good = False
        else:
            print(f"PASS {locale}.json: complete ({ref_count} keys)")

    if all_good:
        print("\nAll locale files are complete.")
        return 0
    else:
        print("\nSome locale files have missing keys. Please add translations.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
