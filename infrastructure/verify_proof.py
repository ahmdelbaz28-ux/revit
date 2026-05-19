#!/usr/bin/env python3
"""
Standalone Deterministic Verifier (CLI) for Regulatory Compliance Proofs.

This tool is completely independent of the FireAlarmAI Governance Engine.
It receives a ComplianceProof JSON and a CanonicalGeoSnapshot JSON, then
mathematically verifies the proof without any network access or trust
in the generating server.

Usage:
    python verify_proof.py --proof proof.json --snapshot snapshot.json
"""

import json
import hashlib
import argparse
import sys


def verify_proof(proof_path: str, snapshot_path: str) -> None:
    """
    Verify a regulatory compliance proof against a geometric snapshot.

    Args:
        proof_path: Path to the ComplianceProof JSON file.
        snapshot_path: Path to the CanonicalGeoSnapshot JSON file.

    Exit codes:
        0: Proof accepted (compliant and untampered).
        1: Proof rejected (tampering detected or geometry mismatch).
    """
    # 1. Read files
    try:
        with open(proof_path, 'r') as f:
            proof = json.load(f)
        with open(snapshot_path, 'r') as f:
            snapshot = json.load(f)
    except FileNotFoundError as e:
        print(f"[ERROR] File not found: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON: {e}")
        sys.exit(1)

    # 2. Verify Geometry Hash (Canonical Serialization)
    # Using sort_keys and strict separators ensures hash determinism
    snapshot_str = json.dumps(snapshot, sort_keys=True, separators=(',', ':'))
    computed_geo_hash = hashlib.sha256(snapshot_str.encode('utf-8')).hexdigest()

    proof_geo_hash = proof.get('geo_hash')
    if computed_geo_hash != proof_geo_hash:
        print(f"[REJECTED] Geometry Hash Mismatch.")
        print(f"  Expected: {proof_geo_hash}")
        print(f"  Computed: {computed_geo_hash}")
        print("  => The CAD geometry has been modified after the proof was issued.")
        sys.exit(1)

    # 3. Verify Proof Token
    # Rebuild the final hash from proof components in the exact same order
    hasher = hashlib.sha256()
    hasher.update(proof.get('clause_id', '').encode('utf-8'))
    hasher.update(proof.get('clause_edition', '').encode('utf-8'))
    hasher.update(proof.get('geo_hash', '').encode('utf-8'))
    hasher.update(proof.get('query_log_hash', '').encode('utf-8'))

    # Serialize 'result' canonically
    result_json = json.dumps(proof.get('result', {}), sort_keys=True, separators=(',', ':'))
    hasher.update(result_json.encode('utf-8'))

    if proof.get('previous_proof_hash'):
        hasher.update(proof.get('previous_proof_hash').encode('utf-8'))

    computed_token = hasher.hexdigest()
    proof_token = proof.get('proof_token')

    if computed_token != proof_token:
        print(f"[REJECTED] Proof Token Invalid.")
        print(f"  Expected: {proof_token}")
        print(f"  Computed: {computed_token}")
        print("  => The proof result or the query log has been tampered with.")
        sys.exit(1)

    # 4. Successful Verification
    print(f"[ACCEPTED] Proof is mathematically valid.")
    print(f"  Clause: {proof.get('clause_id')} ({proof.get('clause_edition')})")
    print(f"  Geometry Hash: {proof_geo_hash} ✓")
    print(f"  Proof Token: {proof_token} ✓")
    print("  => The design is compliant and the proof is untampered.")
    sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Standalone Deterministic Verifier for FireAlarmAI Regulatory Proofs"
    )
    parser.add_argument(
        "--proof", required=True,
        help="Path to the ComplianceProof JSON file"
    )
    parser.add_argument(
        "--snapshot", required=True,
        help="Path to the CanonicalGeoSnapshot JSON file"
    )
    args = parser.parse_args()

    verify_proof(args.proof, args.snapshot)
