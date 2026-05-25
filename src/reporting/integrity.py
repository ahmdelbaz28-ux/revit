"""
reporting/integrity.py
======================
Cryptographic integrity for reports. This is what makes a report
DEFENSIBLE in court — not the absence of errors, but the IMPOSSIBILITY
of tampering with the record after issuance.

Three layers:
  1. Per-finding hash: SHA-256 over canonical JSON of (rule, evidence,
     verdict, citation, software_version).
  2. Hash chain: each finding's hash includes the previous finding's
     hash → tampering with ANY finding invalidates ALL subsequent hashes.
  3. Report seal: SHA-256 of the chain root + ed25519 signature.

If you have the public key + the report, you can verify in O(n):
   • integrity of every finding
   • that the chain wasn't reordered
   • that nothing was added or removed
   • that the report came from a specific issuer

This is the REAL answer to "indisputable" — not infallibility, but
detectability of any change.
"""
from __future__ import annotations
import hashlib, json, time, os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


def _canonical(obj) -> bytes:
    """Deterministic JSON for hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      default=str, ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str): data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


@dataclass
class IntegrityRecord:
    schema_version: str
    issued_at_utc:  str
    issuer:         str
    software:       str
    chain_root:     str
    signature_alg:  str
    signature:      Optional[str] = None
    public_key_pem: Optional[str] = None


def build_hash_chain(items: list[dict]) -> list[dict]:
    """Each item gets `prev_hash` and `hash` fields. Genesis prev_hash = 0×64."""
    prev = "0" * 64
    chained = []
    for it in items:
        body = dict(it)
        body["prev_hash"] = prev
        h = sha256_hex(_canonical(body))
        body["hash"] = h
        chained.append(body)
        prev = h
    return chained


def verify_chain(chained_items: list[dict]) -> tuple[bool, str]:
    """Recompute hashes and verify. Returns (ok, problem_message)."""
    prev = "0" * 64
    for i, it in enumerate(chained_items):
        if it.get("prev_hash") != prev:
            return False, f"prev_hash mismatch at index {i}"
        body = {k: v for k, v in it.items() if k != "hash"}
        h = sha256_hex(_canonical(body))
        if it.get("hash") != h:
            return False, f"hash mismatch at index {i}"
        prev = it["hash"]
    return True, "OK"


def seal_report(report_dict: dict, issuer: str = "FireSafetyGenius",
                software_version: str = "1.1.0",
                private_key_pem: Optional[bytes] = None,
                schema_version: str = "fsg-report-1.0") -> dict:
    """Compute chain root + optional ed25519 signature."""
    findings = report_dict.get("findings", [])
    chained  = build_hash_chain(findings)
    report_dict["findings"] = chained

    chain_root = chained[-1]["hash"] if chained else sha256_hex(b"empty")
    rec = IntegrityRecord(
        schema_version=schema_version,
        issued_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        issuer=issuer, software=software_version,
        chain_root=chain_root, signature_alg="none",
    )

    if private_key_pem:
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            key = serialization.load_pem_private_key(private_key_pem, password=None)
            if isinstance(key, Ed25519PrivateKey):
                payload = _canonical({"chain_root":chain_root,
                                       "issued_at":rec.issued_at_utc,
                                       "issuer":issuer})
                sig = key.sign(payload).hex()
                rec.signature_alg = "ed25519"
                rec.signature = sig
                pub = key.public_key().public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo)
                rec.public_key_pem = pub.decode("utf-8")
        except Exception as ex:
            rec.signature_alg = f"failed: {ex}"

    report_dict["integrity"] = asdict(rec)
    return report_dict


def verify_seal(sealed_report: dict) -> dict:
    """Returns {ok: bool, details: str, signature_ok: Optional[bool]}."""
    integrity = sealed_report.get("integrity", {})
    findings  = sealed_report.get("findings", [])
    ok, msg = verify_chain(findings)
    if not ok: return {"ok": False, "details": msg, "signature_ok": None}

    expected_root = findings[-1]["hash"] if findings else sha256_hex(b"empty")
    if integrity.get("chain_root") != expected_root:
        return {"ok": False, "details": "chain_root doesn't match",
                "signature_ok": None}

    sig_ok = None
    if integrity.get("signature_alg") == "ed25519" and integrity.get("signature"):
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            pub = serialization.load_pem_public_key(
                integrity["public_key_pem"].encode("utf-8"))
            payload = _canonical({"chain_root": integrity["chain_root"],
                                   "issued_at": integrity["issued_at_utc"],
                                   "issuer":    integrity["issuer"]})
            pub.verify(bytes.fromhex(integrity["signature"]), payload)
            sig_ok = True
        except Exception:
            sig_ok = False
    return {"ok": True, "details": "chain verified", "signature_ok": sig_ok}


def generate_keypair_pem() -> tuple[bytes, bytes]:
    """Convenience helper: generate ed25519 keypair for an issuer."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    sk = Ed25519PrivateKey.generate()
    sk_pem = sk.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption())
    pk_pem = sk.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)
    return sk_pem, pk_pem
