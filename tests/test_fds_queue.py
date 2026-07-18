from fastapi.testclient import TestClient

from backend.app import app
from backend.services.fds_queue_service import (
    _compute_webhook_secret,
    get_fds_job_status,
    submit_fds_job,
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

    # Submit job directly through service layer
    res = submit_fds_job(fds_input, project_id="p-123", user_id="u-456")
    assert "job_id" in res
    assert res["status"] in ("simulated", "pending")

    job_id = res["job_id"]

    # Check status via service layer
    status_res = get_fds_job_status(job_id)
    assert status_res["job_id"] == job_id
    assert status_res["project_id"] == "p-123"
    assert status_res["status"] == "simulated"
    assert status_res["result"]["simulation_type"] == "LOCAL_SIMULATION"
    assert status_res["result"]["duration_s"] == 5.0


def test_fds_router_endpoints(monkeypatch):
    """Test the FastAPI router endpoints for FDS queue/webhook."""
    monkeypatch.setenv("FIREAI_API_KEY", "test_dev_key")
    monkeypatch.setenv("FDS_WEBHOOK_SECRET", "test-secret-123456")
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
    assert response.status_code == 200, f"Submit failed: {response.text}"
    data = response.json()
    assert "job_id" in data
    job_id = data["job_id"]

    # Poll status via REST API
    status_response = client.get(f"/api/v2/fds/status/{job_id}", headers=headers)
    assert status_response.status_code == 200, f"Status failed: {status_response.text}"
    status_data = status_response.json()
    assert status_data["job_id"] == job_id

    # Send a mock webhook callback — uses HMAC secret so no API key needed
    secret = _compute_webhook_secret(job_id)
    webhook_payload = {
        "job_id": job_id,
        "status": "completed",
        "secret": secret,
        "result": {
            "max_temperature_c": 120.0,
            "visibility_m": 12.5,
        },
    }

    webhook_response = client.post("/api/v2/fds/webhook", json=webhook_payload)
    assert webhook_response.status_code == 200, f"Webhook failed: {webhook_response.text}"
    assert webhook_response.json()["received"] is True

    # Verify status updated after webhook
    status_response2 = client.get(f"/api/v2/fds/status/{job_id}", headers=headers)
    assert status_response2.status_code == 200
    status_data2 = status_response2.json()
    assert status_data2["status"] == "completed"
    assert status_data2["result"]["max_temperature_c"] == 120.0


def test_fds_webhook_invalid_secret(monkeypatch):
    """Verify that the webhook rejects requests with invalid HMAC secret (returns 400)."""
    monkeypatch.setenv("FDS_WEBHOOK_SECRET", "test-secret-123456")
    job_id = "test-job-uuid"
    webhook_payload = {
        "job_id": job_id,
        "status": "completed",
        "secret": "wrong-secret",
        "result": {},
    }

    response = client.post("/api/v2/fds/webhook", json=webhook_payload)
    # Public endpoint — middleware passes it; handler returns 400 for bad secret
    assert response.status_code == 400, f"Expected 400 for bad secret, got: {response.status_code} — {response.text}"
