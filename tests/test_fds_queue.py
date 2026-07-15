import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app import app
from backend.services.fds_queue_service import (
    submit_fds_job,
    get_fds_job_status,
    handle_fds_webhook,
    _compute_webhook_secret,
)

client = TestClient(app)

def test_fds_local_simulation_job():
    """Verify that submitting an FDS job without Modal runs in local simulation mode."""
    fds_input = """
    &HEAD CHID='test_run', TITLE='Test' /
    &MESH IJK=10,10,10, XB=0,1,0,1,0,1 /
    &TIME T_END=5.0 /
    &TAIL /
    """
    
    # Submit job directly through service
    res = submit_fds_job(fds_input, project_id="p-123", user_id="u-456")
    assert "job_id" in res
    assert res["status"] in ("simulated", "pending")
    
    job_id = res["job_id"]
    
    # Check status
    status_res = get_fds_job_status(job_id)
    assert status_res["job_id"] == job_id
    assert status_res["project_id"] == "p-123"
    assert status_res["status"] == "simulated"
    assert status_res["result"]["simulation_type"] == "LOCAL_SIMULATION"
    assert status_res["result"]["duration_s"] == 5.0

def test_fds_router_endpoints(monkeypatch):
    """Test the FastAPI router endpoints for FDS queue/webhook."""
    # Set the FIREAI_API_KEY environment variable to authenticate the request
    monkeypatch.setenv("FIREAI_API_KEY", "test_dev_key")
    headers = {"X-API-Key": "test_dev_key"}
    
    fds_input = """
    &HEAD CHID='test_run_router', TITLE='Test Router' /
    &TIME T_END=10.0 /
    &TAIL /
    """
    
    # Submit job via REST API
    response = client.post(
        "/api/v2/fds/submit",
        json={"fds_input": fds_input, "project_id": "proj-999"},
        headers=headers,
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    job_id = data["job_id"]
    
    # Poll status
    status_response = client.get(f"/api/v2/fds/status/{job_id}", headers=headers)
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["job_id"] == job_id
    
    # Send a mock webhook callback (bypasses auth because it is in _PUBLIC_PATHS_EXACT)
    secret = _compute_webhook_secret(job_id)
    webhook_payload = {
        "job_id": job_id,
        "status": "completed",
        "secret": secret,
        "result": {
            "max_temperature_c": 120.0,
            "visibility_m": 12.5
        }
    }
    
    webhook_response = client.post(
        "/api/v2/fds/webhook",
        json=webhook_payload,
    )
    assert webhook_response.status_code == 200
    assert webhook_response.json()["received"] is True
    
    # Check status again
    status_response = client.get(f"/api/v2/fds/status/{job_id}", headers=headers)
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["status"] == "completed"
    assert status_data["result"]["max_temperature_c"] == 120.0

def test_fds_webhook_invalid_secret():
    """Verify that the webhook rejects requests with invalid secret (no API key header needed because it is public)."""
    job_id = "test-job-uuid"
    webhook_payload = {
        "job_id": job_id,
        "status": "completed",
        "secret": "wrong-secret",
        "result": {}
    }
    
    response = client.post(
        "/api/v2/fds/webhook",
        json=webhook_payload,
    )
    # The webhook endpoint should return HTTP 400 when invalid
    assert response.status_code == 400
