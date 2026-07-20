"""
backend/services/aps_service.py — Autodesk Platform Services (APS) Integration Service.
====================================================================================

Handles:
1. 2-Legged OAuth Authenticating with Autodesk Developer Platform.
2. Uploading drawing/BIM files to Autodesk Object Storage Service (OSS).
3. Executing Headless Design Automation WorkItems (AutoCAD/Revit cloud processing).
4. Polling WorkItem job status and fetching result files.
"""

from __future__ import annotations

import base64
import logging
import os
import re
import threading
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# ── Singleton Pattern ──────────────────────────────────────────────────────────

_instance: Optional[ApsService] = None
_lock = threading.Lock()


def get_aps_service() -> ApsService:
    """Get the ApsService singleton instance."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = ApsService()
    return _instance


class ApsService:
    """Service to communicate with Autodesk Platform Services (APS) cloud API."""

    def __init__(self) -> None:
        # If credentials are not provided in environment variables, enable simulation mode
        self.client_id = os.getenv("APS_CLIENT_ID", "")
        self.client_secret = os.getenv("APS_CLIENT_SECRET", "")
        self.simulation_mode = not (self.client_id and self.client_secret)

        if self.simulation_mode:
            logger.info("APS Credentials missing. Initializing APS Service in Simulation Mode.")
        else:
            logger.info("APS Service initialized with developer credentials.")

    def get_token(self) -> Dict[str, Any]:
        """
        Authenticate via 2-legged OAuth to get an access token.
        """
        if self.simulation_mode:
            return {
                "success": True,
                "access_token": "mocked_aps_access_token_1234567890",
                "expires_in": 3599,
                "simulation_mode": True
            }

        url = "https://developer.api.autodesk.com/authentication/v2/token"
        auth_bytes = f"{self.client_id}:{self.client_secret}".encode()
        auth_base64 = base64.b64encode(auth_bytes).decode("utf-8")

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {auth_base64}"
        }
        data = {
            "grant_type": "client_credentials",
            "scope": "bucket:create bucket:read data:read data:write code:all"
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(url, data=data, headers=headers)
                if res.status_code == 200:
                    payload = res.json()
                    return {
                        "success": True,
                        "access_token": payload.get("access_token"),
                        "expires_in": payload.get("expires_in"),
                        "simulation_mode": False
                    }
                logger.error("APS OAuth authentication failed: HTTP %s, %s", res.status_code, res.text)
                return {"success": False, "error": f"HTTP {res.status_code}: {res.text}"}
        except Exception as e:
            logger.exception("APS OAuth exception: %s", e)
            return {"success": False, "error": str(e)}

    def create_bucket(self, bucket_key: str, token: str) -> Dict[str, Any]:
        """
        Create a new bucket in Autodesk OSS.
        """
        if self.simulation_mode:
            return {"success": True, "bucketKey": bucket_key, "simulation_mode": True}

        url = "https://developer.api.autodesk.com/oss/v2/buckets"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        payload = {
            "bucketKey": bucket_key,
            "policyKey": "transient"  # Cache for 24 hours
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(url, json=payload, headers=headers)
                if res.status_code in (200, 201, 409):  # 409 means bucket already exists
                    return {"success": True, "bucketKey": bucket_key, "simulation_mode": False}
                return {"success": False, "error": f"HTTP {res.status_code}: {res.text}"}
        except Exception as e:
            logger.exception("APS create bucket error: %s", e)
            return {"success": False, "error": str(e)}

    def upload_file(self, bucket_key: str, object_key: str, file_path: str, token: str) -> Dict[str, Any]:
        """
        Upload local file to Autodesk OSS.
        """
        if self.simulation_mode:
            mock_urn = f"urn:adsk.objects:os.object:{bucket_key}/{object_key}"
            return {
                "success": True,
                "objectId": mock_urn,
                "objectKey": object_key,
                "simulation_mode": True
            }

        url = f"https://developer.api.autodesk.com/oss/v2/buckets/{bucket_key}/objects/{object_key}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream"
        }

        try:
            with open(file_path, "rb") as f:
                data = f.read()

            with httpx.Client(timeout=30.0) as client:
                res = client.put(url, content=data, headers=headers)
                if res.status_code == 200:
                    payload = res.json()
                    return {
                        "success": True,
                        "objectId": payload.get("objectId"),
                        "objectKey": payload.get("objectKey"),
                        "simulation_mode": False
                    }
                return {"success": False, "error": f"HTTP {res.status_code}: {res.text}"}
        except Exception as e:
            logger.exception("APS upload file error: %s", e)
            return {"success": False, "error": str(e)}

    def execute_work_item(self, activity_id: str, input_urn: str, output_urn: str, params: Dict[str, Any], token: str) -> Dict[str, Any]:
        """
        Trigger Design Automation WorkItem.
        """
        if self.simulation_mode:
            mock_work_item_id = f"mock_work_item_{int(time.time())}"
            return {"success": True, "work_item_id": mock_work_item_id, "simulation_mode": True}

        url = "https://developer.api.autodesk.com/da/us-east/v2/workitems"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # Structure parameters mapping inputs and outputs for DA engine
        payload = {
            "activityId": activity_id,
            "arguments": {
                "inputFile": {
                    "url": f"https://developer.api.autodesk.com/oss/v2/buckets/bazspark_inputs/objects/{input_urn.rsplit('/', maxsplit=1)[-1]}",
                    "headers": {
                        "Authorization": f"Bearer {token}"
                    }
                },
                "parameters": {
                    "url": "data:application/json," + httpx.utils.urlencode(params)
                },
                "outputFile": {
                    "url": f"https://developer.api.autodesk.com/oss/v2/buckets/bazspark_outputs/objects/{output_urn.rsplit('/', maxsplit=1)[-1]}",
                    "verb": "put",
                    "headers": {
                        "Authorization": f"Bearer {token}"
                    }
                }
            }
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.post(url, json=payload, headers=headers)
                if res.status_code == 200:
                    work_item_id = res.json().get("id")
                    return {"success": True, "work_item_id": work_item_id, "simulation_mode": False}
                return {"success": False, "error": f"HTTP {res.status_code}: {res.text}"}
        except Exception as e:
            logger.exception("APS WorkItem execution failed: %s", e)
            return {"success": False, "error": str(e)}

    def poll_work_item(self, work_item_id: str, token: str) -> Dict[str, Any]:
        """
        Poll work item execution progress.
        """
        if self.simulation_mode:
            # Simulated progress status sequence
            return {
                "success": True,
                "status": "success",
                "progress": "100%",
                "simulation_mode": True
            }

        # NOSONAR — S7044: work_item_id is validated before reaching this point (UUID format check below)
        # Validate the work_item_id to prevent path traversal
        if not re.match(r'^[a-zA-Z0-9\-_]+$', str(work_item_id)):
            logger.warning("Invalid work_item_id format rejected: %s", str(work_item_id)[:20])
            return {"success": False, "error": "Invalid work item ID format"}

        url = f"https://developer.api.autodesk.com/da/us-east/v2/workitems/{work_item_id}"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url, headers=headers)
                if res.status_code == 200:
                    payload = res.json()
                    return {
                        "success": True,
                        "status": payload.get("status", "pending"),  # pending, success, failedLimitExceeded, etc.
                        "progress": payload.get("progress", "0%"),
                        "reportUrl": payload.get("reportUrl", ""),
                        "simulation_mode": False
                    }
                return {"success": False, "error": f"HTTP {res.status_code}: {res.text}"}
        except Exception as e:
            logger.exception("APS WorkItem status polling exception: %s", e)
            return {"success": False, "error": str(e)}
