from fastapi import FastAPI, HTTPException, UploadFile, File
import json
import hashlib

app = FastAPI(
    title="FireAlarmAI Regulatory Verifier API",
    description="Standalone API endpoint for deterministic compliance verification."
)

@app.post("/api/v1/verify-proof")
async def verify_compliance_proof(
    proof_file: UploadFile = File(...), 
    snapshot_file: UploadFile = File(...)
):
    """
    API Endpoint to deterministically verify a ComplianceProof against a CanonicalGeoSnapshot.
    This adheres to the 'Adding new endpoints' allowed action in the Architecture Freeze.
    """
    try:
        proof_content = await proof_file.read()
        snapshot_content = await snapshot_file.read()
        proof = json.loads(proof_content)
        snapshot = json.loads(snapshot_content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON format: {str(e)}")

    # 1. Verify Geometry Hash (Canonical Serialization)
    snapshot_str = json.dumps(snapshot, sort_keys=True, separators=(',', ':'))
    computed_geo_hash = hashlib.sha256(snapshot_str.encode('utf-8')).hexdigest()
    
    if computed_geo_hash != proof.get('geo_hash'):
        raise HTTPException(
            status_code=403, 
            detail=f"REJECTED: Geometry Hash Mismatch. Expected: {proof.get('geo_hash')}, Got: {computed_geo_hash}"
        )

    # 2. Verify Proof Token
    hasher = hashlib.sha256()
    hasher.update(proof.get('clause_id', '').encode('utf-8'))
    hasher.update(proof.get('clause_edition', '').encode('utf-8'))
    hasher.update(proof.get('geo_hash', '').encode('utf-8'))
    hasher.update(proof.get('query_log_hash', '').encode('utf-8'))
    
    result_json = json.dumps(proof.get('result', {}), sort_keys=True, separators=(',', ':'))
    hasher.update(result_json.encode('utf-8'))
    
    if proof.get('previous_proof_hash'):
        hasher.update(proof.get('previous_proof_hash').encode('utf-8'))
        
    computed_token = hasher.hexdigest()
    
    if computed_token != proof.get('proof_token'):
        raise HTTPException(
            status_code=403, 
            detail="REJECTED: Proof Token Invalid. Compliance logic or result has been tampered with."
        )

    return {
        "status": "ACCEPTED",
        "message": "Proof is mathematically valid and structurally secure.",
        "clause_id": proof.get('clause_id'),
        "verified_geo_hash": computed_geo_hash
    }
