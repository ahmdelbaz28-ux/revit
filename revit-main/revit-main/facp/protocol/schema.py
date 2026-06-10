"""
FACP Protocol Schema Definitions
"""
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import uuid
from datetime import datetime


@dataclass
class FACPSchema:
    """
    Defines the schema for FACP messages
    """
    
    # Request schema
    @staticmethod
    def request_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "protocol": {"type": "string", "const": "FACP/1.0"},
                "type": {"type": "string", "const": "request"},
                "id": {"type": "string"},
                "timestamp": {"type": "string", "format": "date-time"},
                "source": {"type": "string", "enum": ["ide", "agent", "system"]},
                "target": {"type": "string", "enum": ["orchestrator", "engine"]},
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
                        "risk_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]}
                    }
                }
            },
            "required": ["protocol", "type", "id", "timestamp", "source", "target", "method", "params", "security"]
        }
    
    # Response schema
    @staticmethod
    def response_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "protocol": {"type": "string", "const": "FACP/1.0"},
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
                        "engine_version": {"type": "string"},
                        "execution_path": {"type": "array", "items": {"type": "string"}},
                        "latency_ms": {"type": "number"}
                    }
                }
            },
            "required": ["protocol", "type", "id", "status", "trace"]
        }
    
    # Agent message contract schema
    @staticmethod
    def agent_contract_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "role": {"type": "string", "enum": ["planner", "executor", "validator", "optimizer"]},
                "action": {"type": "string", "enum": ["analyze", "compute", "validate", "transform"]},
                "input": {"type": "object"},
                "constraints": {
                    "type": "object",
                    "properties": {
                        "deterministic": {"type": "boolean"},
                        "bounded_execution": {"type": "boolean"},
                        "max_depth": {"type": "number"}
                    }
                }
            },
            "required": ["agent_id", "role", "action", "input", "constraints"]
        }


class FACPSerializationHelper:
    """
    Helper class for serializing/deserializing FACP messages
    """
    
    @staticmethod
    def create_request(
        method: str,
        params: Dict[str, Any],
        source: str = "system",
        target: str = "engine",
        security: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a FACP request message"""
        return {
            "protocol": "FACP/1.0",
            "type": "request",
            "id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "source": source,
            "target": target,
            "method": method,
            "params": params,
            "security": security or {}
        }
    
    @staticmethod
    def create_response(
        req_id: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[Dict[str, str]] = None,
        trace: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a FACP response message"""
        response = {
            "protocol": "FACP/1.0",
            "type": "response",
            "id": req_id,
            "status": status,
            "result": result or {},
            "trace": trace or {}
        }
        if error:
            response["error"] = error
        return response