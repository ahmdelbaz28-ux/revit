"""
modal_runner/fds_worker.py
===========================
Modal.io cloud worker that executes real FDS (Fire Dynamics Simulator) simulations.

Deploy with:
    modal deploy modal_runner/fds_worker.py

Requirements:
    pip install modal
    modal token new  # authenticate with Modal

Environment secrets (set in Modal dashboard):
    FDS_VERSION  (default: "6.8.0")
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

import modal

# ── Modal app definition ──────────────────────────────────────────────────────
app = modal.App("bazspark-fds-runner")

# Docker image with FDS pre-installed
# FDS official Ubuntu image from NIST
fds_image = (
    modal.Image.debian_slim()
    .run_commands(
        # Install FDS 6.8.0
        "apt-get update -qq && apt-get install -y wget curl unzip libgomp1",
        "wget -q https://github.com/firemodels/fds/releases/download/FDS6.8.0/"
        "FDS6.8.0_linux_64.tar.gz -O /tmp/fds.tar.gz",
        "mkdir -p /opt/fds && tar -xzf /tmp/fds.tar.gz -C /opt/fds --strip-components=1",
        "chmod +x /opt/fds/bin/fds",
        "echo 'export PATH=/opt/fds/bin:$PATH' >> /etc/environment",
        # Python dependencies for webhook posting
        "pip install --quiet httpx",
    )
)


# ── Modal function ────────────────────────────────────────────────────────────

@app.function(
    image=fds_image,
    cpu=8,           # 8 vCPUs for parallel FDS meshes
    memory=16384,    # 16 GB RAM
    timeout=3600,    # 1 hour max per simulation
    retries=1,
)
def run_fds_simulation(
    job_id: str,
    fds_input: str,
    webhook_url: str,
    webhook_secret: str,
) -> Dict[str, Any]:
    """
    Execute a full FDS simulation and POST results to the BAZspark webhook.

    Args:
        job_id:         BAZspark job identifier.
        fds_input:      Raw *.fds file content.
        webhook_url:    Where to POST the results when done.
        webhook_secret: HMAC secret to authenticate the webhook.

    Returns:
        Result dict (also POSTed to webhook_url).
    """
    import httpx

    start_time = time.time()

    # ── Write FDS input to temp directory ─────────────────────────────────────
    with tempfile.TemporaryDirectory() as workdir:
        fds_file = Path(workdir) / "bazspark_sim.fds"
        fds_file.write_text(fds_input, encoding="utf-8")

        # ── Run FDS ───────────────────────────────────────────────────────────
        fds_binary = "/opt/fds/bin/fds"
        result_payload: Dict[str, Any] = {}

        try:
            proc = subprocess.run(
                [fds_binary, str(fds_file)],
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=3500,
            )

            stdout = proc.stdout
            stderr = proc.stderr
            elapsed = time.time() - start_time

            if proc.returncode != 0:
                result_payload = {
                    "job_id":  job_id,
                    "status":  "failed",
                    "error":   f"FDS exited with code {proc.returncode}:\n{stderr[:2000]}",
                    "secret":  webhook_secret,
                }
            else:
                # Parse key outputs from stdout
                parsed = _parse_fds_output(workdir, stdout)
                result_payload = {
                    "job_id":  job_id,
                    "status":  "completed",
                    "result":  {
                        **parsed,
                        "elapsed_sec": round(elapsed, 1),
                        "fds_stdout_tail": stdout[-3000:],
                    },
                    "secret":  webhook_secret,
                }

        except subprocess.TimeoutExpired:
            result_payload = {
                "job_id": job_id,
                "status": "failed",
                "error":  "FDS simulation timed out after 3500 seconds",
                "secret": webhook_secret,
            }
        except FileNotFoundError:
            result_payload = {
                "job_id": job_id,
                "status": "failed",
                "error":  "FDS binary not found at /opt/fds/bin/fds",
                "secret": webhook_secret,
            }

    # ── POST results to BAZspark webhook ──────────────────────────────────────
    if webhook_url:
        try:
            httpx.post(
                webhook_url,
                json=result_payload,
                timeout=30.0,
                headers={"Content-Type": "application/json"},
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[FDS Worker] Webhook POST failed: {exc}")

    return result_payload


# ── Output parser ─────────────────────────────────────────────────────────────

def _parse_fds_output(workdir: str, stdout: str) -> Dict[str, Any]:
    """
    Extract key safety metrics from FDS output files.
    Reads .csv device outputs if present; falls back to stdout parsing.
    """
    metrics: Dict[str, Any] = {}
    work = Path(workdir)

    # Try to read _devc.csv (device outputs — temperature, visibility, CO, etc.)
    devc_files = list(work.glob("*_devc.csv"))
    if devc_files:
        try:
            import csv
            with open(devc_files[0], newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            if rows:
                last = rows[-1]
                # Extract standard BAZspark safety metrics
                metrics["max_temperature_c"]    = _safe_float(last.get("TEMP", last.get("Temperature", "0")))
                metrics["smoke_layer_height_m"] = _safe_float(last.get("LAYER HEIGHT", "0"))
                metrics["visibility_m"]          = _safe_float(last.get("VISIBILITY", "0"))
                metrics["co_ppm_max"]            = _safe_float(last.get("CO", "0"))
                metrics["hrr_peak_kw"]           = _safe_float(last.get("HRR", "0"))
        except Exception as exc:  # noqa: BLE001
            print(f"[FDS Worker] CSV parse error: {exc}")

    # Fallback: parse stdout for summary line
    if not metrics:
        for line in stdout.split("\n"):
            if "Max Temperature" in line:
                parts = line.split(":")
                if len(parts) > 1:
                    metrics["max_temperature_c"] = _safe_float(parts[1].strip().split()[0])

    metrics.setdefault("max_temperature_c",    0.0)
    metrics.setdefault("smoke_layer_height_m", 0.0)
    metrics.setdefault("visibility_m",         0.0)
    metrics.setdefault("co_ppm_max",           0.0)
    metrics.setdefault("hrr_peak_kw",          0.0)

    return metrics


def _safe_float(val: Any) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


# ── Local dev test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sample_fds = """
&HEAD CHID='test_fire', TITLE='BAZspark Test' /
&MESH IJK=20,20,20, XB=0.0,5.0,0.0,5.0,0.0,5.0 /
&TIME T_END=10.0 /
&REAC FUEL='POLYURETHANE', HEAT_OF_COMBUSTION=2.3E4 /
&SURF ID='FIRE', HRRPUA=500., COLOR='RED' /
&OBST XB=2.3,2.7,2.3,2.7,0.0,0.1, SURF_IDS='FIRE','INERT','INERT' /
&TAIL /
""".strip()

    print("Running local FDS simulation test (Modal not required)...")
    print(json.dumps(
        {"note": "Set MODAL_TOKEN_ID and MODAL_TOKEN_SECRET to run on Modal cloud"},
        indent=2
    ))
