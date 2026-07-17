"""
backend/services/speckle_service.py — Speckle Cloud Data Integration Service.
=============================================================================

Handles:
1. Connecting to the Speckle Server using API tokens.
2. Pushing AutoCAD/Revit geometry to Speckle streams.
3. Receiving geometries and element metadata from Speckle.
4. Performing layout analysis (NFPA 72 compliance checks) and pushing back fire alarm devices.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Check if specklepy is installed
try:
    from specklepy.api import operations
    from specklepy.api.client import SpeckleClient
    from specklepy.objects import Base
    from specklepy.transports.server import ServerTransport
    HAS_SPECKLE = True
except ImportError:
    HAS_SPECKLE = False
    logger.warning("specklepy not installed. Run: pip install specklepy")

# ── Singleton Pattern ──────────────────────────────────────────────────────────

_instance: Optional[SpeckleService] = None
_lock = threading.Lock()


def get_speckle_service() -> SpeckleService:
    """Get the SpeckleService singleton instance."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = SpeckleService()
    return _instance


class SpeckleService:
    """Service to stream 3D/BIM geometry to and from Speckle Server."""

    def __init__(self) -> None:
        self.simulation_mode = not HAS_SPECKLE
        self._last_stream_id: Optional[str] = None
        self._last_commit_id: Optional[str] = None

    def push_to_speckle(self, stream_id: str, server_url: str, token: str, elements: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Push a list of element dictionaries to a Speckle stream.
        """
        if self.simulation_mode:
            logger.info("Speckle simulation mode: simulated pushing %s elements", len(elements))
            mock_commit = f"mock_commit_{int(time.time())}"
            return {"success": True, "commit_id": mock_commit, "simulation_mode": True}

        try:
            client = SpeckleClient(host=server_url)
            client.authenticate_with_token(token)

            # Create Speckle Base objects
            speckle_elements = []
            for el in elements:
                base_obj = Base()
                for k, v in el.items():
                    base_obj[k] = v
                speckle_elements.append(base_obj)

            commit_root = Base()
            commit_root["@elements"] = speckle_elements

            # Send payload to server transport
            transport = ServerTransport(client=client, stream_id=stream_id)
            obj_id = operations.send(base=commit_root, transports=[transport])

            # Create commit on the branch
            commit_id = client.commit.create(
                stream_id=stream_id,
                object_id=obj_id,
                branch_name="main",
                message=f"BAZspark: Python Backend sync - {len(elements)} elements",
                source_application="PythonBackend"
            )

            self._last_stream_id = stream_id
            self._last_commit_id = commit_id

            return {"success": True, "commit_id": commit_id, "simulation_mode": False}

        except Exception as e:
            logger.exception("Error pushing data to Speckle: %s", e)
            return {"success": False, "error": str(e)}

    def receive_from_speckle(self, stream_id: str, server_url: str, token: str) -> Dict[str, Any]:
        """
        Pull the latest commit elements list from the main branch of a Speckle stream.
        """
        if self.simulation_mode:
            logger.info("Speckle simulation mode: returning mock structural geometry")
            return {
                "success": True,
                "elements": [
                    {"id": "1", "type": "Wall", "x": 0.0, "y": 0.0},
                    {"id": "2", "type": "Wall", "x": 5000.0, "y": 0.0}
                ],
                "simulation_mode": True
            }

        try:
            client = SpeckleClient(host=server_url)
            client.authenticate_with_token(token)

            # Retrieve branch details
            branch = client.branch.get(stream_id, "main", 1)
            if not branch or not branch.commits or not branch.commits.items:
                return {"success": True, "elements": [], "message": "Stream branch main is empty."}

            referenced_object = branch.commits.items[0].referencedObject

            # Receive model payload
            transport = ServerTransport(client=client, stream_id=stream_id)
            commit_root = operations.receive(obj_id=referenced_object, remote_transport=transport)

            if not commit_root:
                return {"success": False, "error": "Failed to receive commit root object."}

            # Gather elements
            raw_elements = commit_root.get("@elements") or commit_root.get("elements") or []
            elements = []
            for obj in raw_elements:
                if isinstance(obj, Base):
                    # Convert Speckle Base back to dictionary
                    elements.append(obj.to_dict())

            return {"success": True, "elements": elements, "simulation_mode": False}

        except Exception as e:
            logger.exception("Error receiving data from Speckle: %s", e)
            return {"success": False, "error": str(e)}
