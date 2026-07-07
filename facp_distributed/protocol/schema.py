# NOSONAR
"""FACP Distributed Protocol Schema Definitions"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class FACPDistributedSchema:
    """Defines the schema for distributed FACP messages"""

    # Enhanced Request schema for distributed system
    @staticmethod
    def request_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "protocol": {"type": "string", "const": "FACP/1.1"},  # NOSONAR — S1192: duplicated literal acceptable in this localized context
                "type": {"type": "string", "const": "request"},
                "id": {"type": "string"},
                "timestamp": {"type": "string", "format": "date-time"},
                "source": {"type": "string", "enum": ["l1", "l2", "l3", "client", "orchestrator", "engine"]},
                "target": {"type": "string", "enum": ["orchestrator", "engine", "client"]},
                "execution_state": {
                    "type": "string",
                    "enum": ["RECEIVED", "VALIDATED", "ROUTED", "EXECUTING", "COMPLETED", "FAILED"]
                },
                "method": {"type": "string"},
                "params": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "payload": {"type": "object"},
                        "context": {"type": "object"}
                    },
                    "required": ["task"]
                },
                "security": {
                    "type": "object",
                    "properties": {
                        "auth_token": {"type": ["string", "null"]},
                        "permissions": {"type": "array", "items": {"type": "string"}},
                        "risk_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                        "idempotency_key": {"type": ["string", "null"]}
                    }
                },
                "constraints": {
                    "type": "object",
                    "properties": {
                        "timeout_ms": {"type": "integer", "minimum": 1},
                        "max_memory_mb": {"type": "number", "minimum": 0.1},
                        "max_recursion_depth": {"type": "integer", "minimum": 1}
                    }
                }
            },
            "required": ["protocol", "type", "id", "timestamp", "source", "target", "execution_state", "method", "params", "security", "constraints"]
        }

    # Enhanced Response schema for distributed system
    @staticmethod
    def response_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "protocol": {"type": "string", "const": "FACP/1.1"},
                "type": {"type": "string", "const": "response"},
                "id": {"type": "string"},
                "status": {"type": "string", "enum": ["success", "error"]},
                "result": {"type": "object"},
                "error": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "message": {"type": "string"}
                    },
                    "required": ["code", "message"]
                },
                "trace": {
                    "type": "object",
                    "properties": {
                        "execution_path": {"type": "array", "items": {"type": "string"}},
                        "latency_ms": {"type": "number"},
                        "node_id": {"type": "string"},
                        "engine_version": {"type": "string"}
                    }
                }
            },
            "required": ["protocol", "type", "id", "status", "trace"]
        }


class FACPDistributedSerializationHelper:
    """Helper class for serializing/deserializing distributed FACP messages"""

    @staticmethod
    def create_request(
        method: str,
        params: Dict[str, Any],
        source: str = "client",
        target: str = "engine",
        execution_state: str = "RECEIVED",
        security: Optional[Dict[str, Any]] = None,
        constraints: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a distributed FACP request message"""
        return {
            "protocol": "FACP/1.1",
            "type": "request",
            "id": str(uuid.uuid4()),
            # Timezone-aware UTC timestamp (avoids the deprecated naive-UTC API).
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "target": target,
            "execution_state": execution_state,
            "method": method,
            "params": params,
            "security": security or {},
            "constraints": constraints or {
                "timeout_ms": 8000,
                "max_memory_mb": 512,
                "max_recursion_depth": 5
            }
        }

    @staticmethod
    def create_response(
        req_id: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[Dict[str, str]] = None,
        trace: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a distributed FACP response message"""
        response = {
            "protocol": "FACP/1.1",
            "type": "response",
            "id": req_id,
            "status": status,
            "result": result or {},
            "trace": trace or {}
        }
        if error:
            response["error"] = error
        return response
