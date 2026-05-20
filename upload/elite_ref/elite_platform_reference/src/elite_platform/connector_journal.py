"""Connector journal that makes BIM drift explicit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ConnectorRevision:
    connector_name: str
    external_model_id: str
    revision_id: str
    snapshot_id: str


class ConnectorJournal(object):
    def __init__(self):
        self._entries = []

    def register_revision(self, connector_name, external_model_id, revision_id, snapshot_id):
        entry = ConnectorRevision(
            connector_name=connector_name,
            external_model_id=external_model_id,
            revision_id=revision_id,
            snapshot_id=snapshot_id,
        )
        self._entries.append(entry)
        return entry

    def latest_for_model(self, external_model_id):
        for entry in reversed(self._entries):
            if entry.external_model_id == external_model_id:
                return entry
        return None

    def detect_revision_drift(self, external_model_id, observed_revision_id):
        latest = self.latest_for_model(external_model_id)
        if latest is None:
            return {
                "status": "unknown_model",
                "external_model_id": external_model_id,
                "observed_revision_id": observed_revision_id,
            }
        if latest.revision_id == observed_revision_id:
            return {
                "status": "in_sync",
                "external_model_id": external_model_id,
                "revision_id": observed_revision_id,
                "snapshot_id": latest.snapshot_id,
            }
        return {
            "status": "drift_detected",
            "external_model_id": external_model_id,
            "expected_revision_id": latest.revision_id,
            "observed_revision_id": observed_revision_id,
            "snapshot_id": latest.snapshot_id,
        }
