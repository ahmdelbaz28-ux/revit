"""Deterministic serialization helpers."""

from __future__ import annotations

import hashlib
import json


def canonical_dumps(payload):
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def sha256_payload(payload):
    return hashlib.sha256(canonical_dumps(payload).encode("utf-8")).hexdigest()
